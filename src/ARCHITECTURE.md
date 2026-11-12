# Linux iCloud Photos 0.15.0 - przewodnik po kodzie

Ten plik opisuje, jak aplikacja jest zbudowana i gdzie w kodzie szukać poszczególnych rzeczy.
Numery linii dotyczą wersji 0.9.1 (mogą się przesuwać po zmianach).

## 1. Pliki

| Plik | Linii | Za co odpowiada |
|---|---|---|
| `app.py` | 3272 | Cały interfejs GTK4/libadwaita: okno główne, podgląd, pokaz slajdów, okna dialogowe |
| `backend.py` | 730 | Wszystko, co dotyka iCloud: logowanie, listy, pobieranie, cache, proxy wideo, operacje grupowe. **Nie importuje GTK** (czysty Python), więc da się to testować bez okna |
| `cast.py` | 166 | Wysyłanie na TV przez DLNA/UPnP (SSDP + SOAP, bez zależności) |
| `cast_gc.py` | 46 | Chromecast przez `pychromecast` |
| `airplay.py` | 223 | AirPlay (Apple TV) przez `pyatv`: parowanie PIN-em, wideo, zdjęcia (eksperymentalnie) |
| `i18n.py` | ok. 420 | Język interfejsu (polski/angielski/niemiecki/ukraiński), tabela `EN`, odmiana, miesiące |
| `i18n_de.py`, `i18n_uk.py` | po ok. 250 | Tabele niemiecka i ukraińska (klucz = angielski napis) |
| `pick.py` | 180 | Tryb wyboru `--pick` dla innych aplikacji (linux-whazzapp): opcje CLI, eksport zaznaczonych plików (HEIC→JPEG, wideo H.264, Live Photo jako zdjęcie), wynik JSON. Bez GTK poza dekodowaniem HEIC |
| `bridge.py` | 230 | Most dla innych aplikacji bez okna (linux-skytrack): lista albumów, miniatury albumu albo zakresu dat, tworzenie albumu ze zdjęć z podanych dni, wysyłanie pliku do folderu w iCloud Drive (0.16.0, kopie zapasowe SkyTrack). Zapisana sesja, nigdy nie pyta o hasło/2FA (błąd `login_required`). Wynik JSON. Wywoływany z `app.py` przed importem GTK |
| `exif.py` | 100 | Własny, minimalny parser EXIF (JPEG/HEIC) - model telefonu, obiektyw, ekspozycja, GPS |
| `version.py` | 2 | `VERSION` i `DATE` (pokazywane na dole menu; czyta je też `build-deb.sh`) |
| `packaging/` | | `launcher`, `postinst`/`postrm`, `control`, plik `.desktop`, ikona SVG, `copyright` |
| `flatpak/` | | Manifest, metainfo, skrypty budowania i usuwania (nieprzetestowane) |
| `build-deb.sh` | 33 | Składa paczkę `.deb` |

Zależności zewnętrzne: `pyicloud` (nieoficjalne API iCloud), `keyring`, `pychromecast`, `pyatv`
(te trzy ostatnie opcjonalne), systemowo GTK4, libadwaita, PyGObject, GStreamer, `mpv`.

## 2. Jak to działa w skrócie

    Użytkownik ──► GTK (wątek główny)  ──bg(fn, cb)──►  wątek roboczy ──► backend.ICloud ──► pyicloud ──► Apple
                         ▲                                      │
                         └────── GLib.idle_add(cb, wynik) ◄─────┘

Najważniejsza zasada: **widgety GTK dotykamy tylko w wątku głównym**. Każda wolna rzecz (sieć, dysk)
idzie przez `bg(fn, cb)` (`app.py:95`): `fn` leci w wątku, a wynik `(wynik, błąd)` wraca do `cb`
w wątku głównym przez `GLib.idle_add`.

Wątki i pule:
- `POOL` (6 wątków, `app.py:48`) - miniatury kafelków.
- `COVER_POOL` (3 wątki, `app.py:49`) - okładki albumów.
- osobna pętla `asyncio` w wątku w tle - tylko AirPlay (`airplay.py`, `_get_loop`).
- `ThreadingHTTPServer` w wątkach - proxy wideo (patrz niżej).
- Skanowanie sieci (DLNA, Chromecast, AirPlay) - krótka pula 3 wątków w `_discover_all`.

## 3. Backend (`backend.py`, klasa `ICloud`)

**Logowanie** (`login`, `verify_2fa`): tworzy `PyiCloudService` z katalogiem ciasteczek
`~/.config/linux-icloud-photos/session`. Hasło trzyma `keyring` (usługa `linux-icloud-photos`), ID Apple
w `config.json`. Dzięki zapisanej sesji kolejne starty często nie proszą o kod 2FA.

**Listowanie** (`albums`, `iter_assets`, `total`): `iter_assets` to leniwy generator. Ustawia kierunek
albumu (`album._direction`), bo Apple zwraca różne albumy w różnej kolejności (tylko "Wszystkie zdjęcia"
jest domyślnie malejące). Aplikacja czyta go partiami (`BATCH = 300`).

**Pobieranie obrazów i cache** (`fetch`, `_cache_path`): ścieżka pliku to `sha1(id:wersja)`. Wersje to klucze
pyicloud: dla zdjęć `thumb`/`medium`/`original`, dla filmów **`thumb_image`/`medium_image`** (bo `thumb`
i `medium` filmu to same pliki wideo). Cache: `~/.cache/linux-icloud-photos/{thumbs,medium,live,videos}`.
`prune_cache` przy starcie usuwa najstarsze (po `mtime`) aż całość zejdzie poniżej 90% limitu
(`cache_gb`, domyślnie 1 GB).

**Wideo** (`stream_url`, `_ensure_server`): lokalny serwer HTTP z obsługą `Range`, który przekazuje strumień
z CDN Apple, używając sesji pyicloud (ciasteczka). Adres ma postać
`http://127.0.0.1:PORT/<losowy token>`. mpv dostaje ten adres. Token to `secrets.token_urlsafe(16)`,
tokenów trzymamy maksymalnie 300. Drugi serwer (`0.0.0.0`) powstaje **tylko przy wysyłaniu na TV** -
to jedyny moment, gdy aplikacja nasłuchuje w sieci lokalnej.

**Plan B dla filmów** (`fetch_video_file`): gdy streaming przez mpv zawiedzie, film jest pobierany do
`videos/` oficjalną ścieżką pyicloud i odtwarzany lokalnie. **Live Photo** (`fetch_live`) działa podobnie:
krótki klip `.mov` do cache i odtwarzanie lokalne.

**Skok do daty** (`find_start`, `iter_jump`): wyszukiwanie binarne po pozycji w albumie; każde sondowanie
to `album._get_photos_at(i, ASC, 1)`, razem ok. log2(n) zapytań (≈17 przy 12 tys.). Wykrywa, czy daty
rosną czy maleją wraz z pozycją, a potem czyta album od znalezionego miejsca. `parse_date_query`
rozpoznaje daty wpisane w wyszukiwarce.

**Operacje grupowe**: `add_to_album` (najpierw `album_member_ids` czyta cały album i pomija duplikaty,
potem `add_photo`), `set_favorite`, `save_originals` (strumieniowo na dysk, bez ładowania całości do RAM),
`upload` (`album.upload()` albo `library.all.upload()`).

**Metadane** (`asset_info`, `read_exif`, `reverse_geocode`): lokalizacja z pól rekordu iCloud, telefon
z EXIF podglądu (a gdy go nie ma - z oryginału na żądanie). Nazwa miejsca idzie do OpenStreetMap
Nominatim **tylko po kliknięciu**.

**Układ rzędów**: `justify_rows` (czysta funkcja, `backend.py:118`) i `asset_aspect` (proporcje z wymiarów
i pola `orientation`; dla orientacji 5-8 zamienia szerokość z wysokością).

**Sesja wygasła**: `is_auth_error` rozpoznaje wyjątki po nazwie klasy i treści (`probe` to lekkie
zapytanie sprawdzające, czy sesja żyje).

## 4. Interfejs (`app.py`)

Mapa klas i funkcji:

| Linie | Co |
|---|---|
| 70-110 | `load_cfg`/`save_cfg` (config JSON), `_auth_check`, **`bg`** |
| 113-176 | `PhotoObj` (zdjęcie + proporcje), `RowObj`/`RowBox` (rząd), `TexCache` (600 tekstur w RAM), `make_texture` |
| 178 | `Tile` - kafelek: obraz, odznaki (wideo, LIVE), ptaszek zaznaczenia, gesty (prawy klik, kliknięcie) |
| 247 | `ZoomView` - powiększanie (rozmiar zawartości w `ScrolledWindow`), przeciąganie, szczypanie |
| 388 | `Viewer` - okno podglądu: zoom, wideo, Live Photo, przyciski, klawisze |
| 799 | `Slideshow` - pokaz slajdów (dwie `Gtk.Picture` w `Gtk.Stack` z przenikaniem) |
| 1008-1507 | Okna dialogowe: `UploadDialog`, `InfoDialog`, `SettingsDialog`, `AddToAlbumDialog`, `PairingDialog` |
| 1507 | `AlbumRow` - wiersz menu (okładka 40x40 albo ikona) |
| **1555-3247** | **`MainWindow` - serce aplikacji (opis niżej)** |
| 3248 | `App` - start: CSS, ikona, sprzątanie cache |

`MainWindow` według obszarów (numery metod):
- **Logowanie i sesja**: `_build_login`, `_autologin`, `on_login`, `_after_login`, `_after_2fa`, `logged_in`,
  `on_auth_error` → `session_expired`.
- **Menu albumów**: `_build_main`, `_albums_loaded`, `_load_covers`, `_on_album_selected`, `_row_filter`/`_on_search`.
- **Lista zdjęć**: `load_album`, `_load_more`, `_maybe_more`, `_check_order`, `_toggle_sort`.
- **Siatka kafelków**: `_build_grid`, `_make_factory`, `_bind_tile`/`_unbind_tile` (wspólne z rzędami), `set_tile_size`.
- **Układ rzędów**: `_apply_layout`, `_make_rows_factory`, `_bind_row`, `_rows_sync`, `_rows_watch`.
- **Zaznaczanie**: `set_select_mode`, `_toggle_tile`, `_install_rubberband`, `_rb_begin`/`_rb_update`/`_rb_recompute`/`_rb_end`.
- **Operacje na zaznaczeniu / albumach**: `_sel_*`, `add_to_album_async`, `album_menu_entries`, `remember_album`.
- **TV**: `_build_cast`, `_discover_all`, `_cast_pick`, `cast_asset`.
- **Wideo**: `play_external`, `_video_plan_b`, `external_video_ok`.
- **Skok do daty**: `_build_jump_button`, `_jump_from_query`, `_do_jump`.

### Kilka mechanizmów wartych zrozumienia

**Nieskończone przewijanie.** `load_album` tworzy generator (`self.it`) i ładuje pierwszą partię.
`_maybe_more` (podpięte do `value-changed` i `changed` pionowego `Adjustment` okna przewijania) dociąga
kolejną partię, gdy do końca zostało mniej niż 3 wysokości okna. Dzięki temu 12 tys. zdjęć nie jest
pobieranych naraz. Po pierwszej partii `_check_order` porównuje daty i w razie odwrotnej kolejności
przeładowuje album z odwróconym założeniem.

**Wirtualizacja.** Zarówno `Gtk.GridView`, jak i `Gtk.ListView` (rzędy) tworzą widgety tylko dla widocznych
elementów i **recyklują je**. Dlatego stan nie leży w widgetach, tylko w `PhotoObj`; kafelek jest
"wiązany" (`_bind_tile`) i "odwiązywany" (`_unbind_tile`, który anuluje trwające pobieranie).

**Układ rzędów.** `justify_rows` dzieli listę zdjęć na rzędy o jednakowej wysokości, tak by suma szerokości
wypełniała okno. `_rows_sync` przy dopisaniu zdjęć liczy tylko od ostatniego (niepełnego) rzędu, a przy
zmianie szerokości, rozmiaru lub kolejności buduje wszystko od nowa i próbuje zachować położenie przewijania.

**Zaznaczanie ramką.** Jeden `Gtk.GestureDrag` w fazie CAPTURE na oknie przewijania. Geometria jest liczona
we współrzędnych widoku listy (`self.grid`), więc działa tak samo w kafelkach i rzędach. Dla każdej klatki
sprawdza przecięcie z widocznymi kafelkami (`compute_bounds`). Kafelki, które wyjechały poza ekran,
zachowują ostatnią decyzję. Gest "zabiera" sekwencję zdarzeń (`CLAIMED`), żeby kliknięcie nie otwierało podglądu.

**Wygasła sesja.** `bg()` sprawdza każdy wyjątek funkcją `is_auth_error`. Przy podejrzeniu woła hook
`on_auth_error`, który robi lekkie zapytanie kontrolne (`probe`). Dopiero gdy ono potwierdzi wygaśnięcie,
`session_expired` czyści widok i wraca do logowania, próbując zalogować się zapisanym hasłem. Dzięki
zapytaniu kontrolnemu pojedynczy zły adres zdjęcia nie wylogowuje.

**Wysyłanie na TV.** `cast_asset` wybiera wersję pliku (JPEG, albo H.264 dla wideo), buduje adres z IP tego
komputera (`lan_ip_for`) na serwerze LAN (`stream_url(..., lan_host=ip)`) z końcówką `/photo.jpg` lub
`/video.mp4`, po czym woła `play_uri` wybranego urządzenia. Trzy implementacje (`cast.Renderer`,
`cast_gc.ChromecastTarget`, `airplay.AirPlayTarget`) mają ten sam interfejs: `name`, `host`, `kind`,
`play_uri(...)`, `stop()`.

## 4a. Języki interfejsu (`i18n.py`)

Teksty w kodzie są po polsku i owinięte w `tr("...")`. Dla polskiego `tr()` zwraca napis bez zmian. Dla innych
języków szuka angielskiego odpowiednika w słowniku `EN` (klucz = polski napis), a niemiecki (`i18n_de.py`) i
ukraiński (`i18n_uk.py`) tłumaczą dalej ten angielski tekst (klucz = angielski napis). Automatycznie wybierane są
tylko polski i angielski; niemiecki i ukraiński - ręcznie w Ustawieniach albo przez `ICLOUD_PHOTOS_LANG`. Język wybierany jest raz, przy
imporcie modułu (dlatego zmiana wymaga restartu), w kolejności: zmienna `ICLOUD_PHOTOS_LANG`, ustawienie
`language` w `config.json` (zmieniane w Ustawieniach), potem język systemu (`LANGUAGE`, `LC_ALL`,
`LC_MESSAGES`, `LANG`).

Zasady, które trzeba znać przy dopisywaniu tekstów:
- Napisy z podstawieniami to szablony z **numerowanymi** miejscami: `tr("Dodano {0} z {1}").format(a, b)`
  (nigdy f-string wewnątrz `tr()`, bo byłby podstawiony przed tłumaczeniem).
- Gdy ten sam polski napis znaczy co innego, dopisz kontekst po kresce: `tr("Wideo|typ")`. Po polsku kontekst
  jest obcinany.
- Odmiana liczebników: `plural(n, ("zdjęcie", "zdjęcia", "zdjęć"), ("photo", "photos"))`.
- Nazwy miesięcy: `month_names()` i `month_abbr()`.
- Nowy tekst = nowy wpis w `EN`. Po zmianach uruchom `python3 tools/check_i18n.py`: wykryje brakujące
  tłumaczenia, nieużywane wpisy, niezgodne miejsca na podstawienia i polskie napisy zostawione poza `tr()`.
- Komunikaty dla programisty (`log.info(...)`) zostają po polsku i nie są tłumaczone.
- Teksty widgetów GTK (np. okno wyboru pliku) tłumaczy sam GTK według języka systemu.

## 4a2. Przezroczystość okna

`MainWindow.set_glass(0-100)`: poziom 0 = wygląd jak dotąd. Wyższy poziom dodaje klasę CSS `glass` (tło okna i panele
dostają kanał alfa; panele są mniej przezroczyste niż tło, by tekst był czytelny) oraz włącza `Backdrop` -
widget pod całym interfejsem, który rysuje bardzo małą, uśrednioną kopię pierwszej miniatury bieżącego albumu
rozciągniętą na okno (`blur_texture`, wygładzanie TRILINEAR), czyli miękkie plamy kolorów bez kosztownego rozmycia
w trakcie rysowania. Prawdziwego rozmycia pulpitu za oknem aplikacja GTK4 na GNOME zrobić nie może. Test mierzy kanał
alfa wyrenderowanego okna.

## 4b. Usuwanie zdjęć

`ICloud.delete_assets` wywołuje `asset.delete()` z pyicloud (ustawia `isDeleted=1`, czyli zdjęcie trafia do
„Ostatnio usunięte”), a potem POTWIERDZA to jednym zapytaniem `lookup` na paczkę do 100 rekordów
(`_confirm_deleted` sprawdza `isDeleted=1`). Samo `delete()` nie wystarcza, bo starsza ścieżka pyicloud zwraca
sukces bez sprawdzania odpowiedzi serwera. Dopiero potwierdzone zdjęcia znikają z widoku (`MainWindow._do_delete`).

UWAGA: do potwierdzania NIE wolno używać `library.get(id)`. Dla zdjęcia, którego już nie ma, pyicloud po nieudanym
zapytaniu przegląda CAŁĄ bibliotekę (setki zapytań), co w wersji 0.11.0 powodowało wielominutowe „wiszenie”.
Test `delete_backend_test` pilnuje, żeby biblioteka nie była dotykana.

Wejścia: pasek zaznaczania, menu prawego przycisku, przycisk i klawisz `Delete` w podglądzie. Zawsze przez
`MainWindow.confirm_delete` (okno z domyślnym „Anuluj”). W albumie „Ostatnio usunięte” usuwanie jest wyłączone.
Aplikacja nie przywraca zdjęć (pyicloud nie ma takiej funkcji) - to się robi w aplikacji Zdjęcia lub na iCloud.com.

## 4c. Instalacja i środowisko Pythona

Pakiet tworzy prywatne środowisko w `/opt/linux-icloud-photos/venv` (`packaging/postinst`). Biblioteki są przypięte:
`requirements.txt` (pyicloud, keyring), `requirements-optional.txt` (Chromecast, AirPlay) i `constraints.txt`
(pełna lista z zależnościami pośrednimi, wygenerowana w czystym środowisku Python 3.12). Instalator próbuje po
kolei: dokładne wersje, same przypięte biblioteki główne, najnowsze (z ostrzeżeniem). `postinst` uruchamia się
przy instalacji, przy `dpkg-reconfigure` i - przez plik `triggers` (`interest-noawait /usr/bin/python3`) -
przy każdej aktualizacji systemowego Pythona; gdy wersja Pythona się zmieniła, środowisko jest budowane od nowa.
Launcher (`packaging/launcher`) sprawdza, czy środowisko działa, i jeśli nie, pokazuje polecenie naprawcze.
Przy starcie `check_versions()` sprawdza minimalne wersje GTK 4.10 i libadwaita 1.2.

## 4d. Testy

`tests/scripts/` zawiera skrypty testowe (sztuczny iCloud w atrapach), `tests/run_tests.py` uruchamia je w
izolowanym HOME i porównuje z wzorcami z `tests/golden/`. Wzorzec zawiera tylko linie, które były identyczne
w uruchomieniach przy różnym wyglądzie (zwykłym i ciemny motyw + większa czcionka + klasyczne paski
przewijania), więc wartości zależne od motywu nie dają fałszywych alarmów na innej wersji systemu.
Po zamierzonej zmianie zachowania: `python3 tests/run_tests.py --update`. CI: `.github/workflows/ci.yml`.

## 4e. Odświeżanie biblioteki i pokaz slajdów

`MainWindow.refresh_library` (przycisk na belce, `F5`, `Ctrl+R`) woła `ICloud.refresh_library`: pyicloud trzyma listę
albumów w pamięci, więc wywoływane jest jego `refresh_albums()`, a zapisane okładki są zapominane (`covers.json`).
Potem `_albums_loaded` odbudowuje menu i zaznacza ponownie album z `_keep_key`, co przeładowuje jego zdjęcia.
Błąd uwierzytelnienia przy odświeżaniu przenosi do logowania (`session_expired`), inny błąd tylko pokazuje komunikat.
Pokaz slajdów nie ma przycisku na belce: startuje z podglądu (`Viewer._start_slideshow_here`) albo z menu prawego
przycisku (`MainWindow._slideshow_from`).

## 4f. Nazwa, migracja danych i licencja

Od 0.12.2 aplikacja nazywa się „Linux iCloud Photos”: pakiet, polecenie i katalogi to `linux-icloud-photos`, a
identyfikator aplikacji i plików Flatpaka to `local.linuxicloudphotos.Photos`. Stara nazwa (`icloud-photos-linux`)
występuje już tylko w migracji: `backend.migrate_old_data()` przenosi stare katalogi konfiguracji i cache
(wykonywane przy imporcie backendu i tylko gdy nowy katalog nie istnieje), `i18n._config_language()` czyta język
także ze starego katalogu (i18n ładuje się przed backendem), a hasło Apple ID (`app.OLD_KEYRING_SERVICE`) i dane
parowania AirPlay (`airplay.OLD_KEYRING_SERVICE`) są odczytywane ze starej nazwy usługi i kopiowane pod nową.
Pakiet `.deb` ma `Replaces`/`Conflicts` na stary pakiet, więc instalacja nowego usuwa stary. Test:
`tests/scripts/rename_migration_test.py`.

Licencja (`LICENSE`, ten sam tekst w `packaging/copyright`): bezpłatna, rozpowszechnianie tylko w niezmienionej
formie, modyfikacje zabronione; komponenty zewnętrzne zostają na własnych licencjach. Wersje do 0.12.1 były na MIT.
W `flatpak/*.metainfo.xml` pole `project_license` to `LicenseRef-proprietary`.

## 4g. Tryb wyboru (`--pick`, 0.14.0)

`app.py` w `__main__` wywołuje `pick.parse_cli(sys.argv)`; gdy jest `--pick`, ustawia `backend.READ_ONLY = True`
(`_guard_write()` blokuje `upload`, `add_to_album`, `set_favorite`, `delete_assets`) i globalne `PICK`.
Po zalogowaniu `_enter_pick_mode()` włącza stały tryb zaznaczania z paskiem „Wybierz”; `_pick_confirm()` eksportuje
pliki w wątku (`bg`), zapisuje JSON (`pick.write_result`) i kończy aplikację kodem 0. Zamknięcie okna lub Esc bez
zaznaczenia zapisuje wynik `cancelled` i daje kod 1. W tym trybie aplikacja startuje jako `NON_UNIQUE`, żeby
działała obok zwykłego okna. Testy: `tests/scripts/pick_test.py` i `pick_ui_test.py`.

## 5. Dane na dysku

| Co | Gdzie |
|---|---|
| Ustawienia | `~/.config/linux-icloud-photos/config.json` (klucze: `apple_id`, `tile`, `layout`, `newest_first`, `fit_original`, `sidebar_w`, `slide_secs`, `cache_gb`, `video_player`, `recent_albums`, `embedded_video`, `language`) |
| Sesja Apple | `~/.config/linux-icloud-photos/session/` |
| Hasło | systemowy keyring (usługa `linux-icloud-photos`) |
| Parowanie AirPlay | keyring (`linux-icloud-photos-airplay`), a bez niego `~/.config/linux-icloud-photos/airplay.json` (0600) |
| Cache obrazów | `~/.cache/linux-icloud-photos/{thumbs,medium,live,videos}`, `covers.json` |
| Dziennik | `~/.cache/linux-icloud-photos/debug.log` (obracany, 512 KB) i `mpv.log` |

## 6. Prywatność i bezpieczeństwo - co warto wiedzieć

- Aplikacja łączy się z serwerami Apple (przez `pyicloud`). Dodatkowo, **tylko na życzenie**: z OpenStreetMap
  (nazwa miejsca po kliknięciu) i z urządzeniami w Twojej sieci lokalnej (TV).
- Proxy wideo słucha tylko na `127.0.0.1`, a adres chroni losowy token. Serwer na `0.0.0.0` powstaje dopiero
  przy wysyłaniu na TV i działa do zamknięcia aplikacji; osoby w tej samej sieci mogłyby pobrać plik,
  gdyby znały losowy token (16 bajtów), więc ryzyko jest małe, ale nie zerowe.
- Zdjęcia nie są synchronizowane na dysk. Zostają tylko miniatury/podglądy/klipy w cache (limit w ustawieniach)
  i pliki, które sam zapiszesz ("Zapisz oryginał").
- API jest **nieoficjalne**: Apple może je zmienić bez ostrzeżenia, a Advanced Data Protection musi być wyłączone.

## 7. Pakowanie

`build-deb.sh` składa `/usr/lib/linux-icloud-photos/*.py`, launcher `/usr/bin/linux-icloud-photos`,
plik `.desktop`, ikonę i dokumentację. `postinst` tworzy venv w `/opt/linux-icloud-photos/venv`
(z `--system-site-packages`, żeby widział PyGObject) i instaluje przez `pip` pakiety `pyicloud`, `keyring`
oraz opcjonalnie `pychromecast` i `pyatv`. Launcher uruchamia `app.py` interpreterem z tego venv.

## 8. Jak to testowałem (i czego nie)

Testy uruchamiałem w piaskownicy na **atrapach** zamiast prawdziwego iCloud: sztuczna klasa `ICloud`
z wygenerowanymi zdjęciami, lokalny serwer udający CDN z obsługą `Range`, atrapa `mpv`, atrapy
`pyatv`/`pychromecast`, a interfejs w wirtualnym ekranie (Xvfb). Pliki testowe **nie są dołączone**
(są sztywno związane ze ścieżkami piaskownicy).

**Niesprawdzone na prawdziwym sprzęcie:** logowanie i 2FA z prawdziwym kontem w pełnym zakresie, dokładne
zachowanie CDN Apple przy wideo, odtwarzanie dźwięku/obrazu w GTK, Chromecast, AirPlay, DLNA na prawdziwym TV,
Flatpak. Granica między tym, co sprawdzone, a tym, co nie, to zwykle granica "atrapa vs prawdziwy Apple".

## 9. Gdzie coś zmienić

- Domyślny limit cache: `MAX_CACHE_BYTES` w `backend.py` (a użytkownik zmienia go w Ustawieniach).
- Wielkość partii ładowania: `BATCH` w `app.py:50`.
- Presety rozmiaru siatki: `PRESETS` (`app.py:52`), zakres suwaka: `TILE_MIN`/`TILE_MAX`.
- Odstępy pokazu slajdów: `SLIDE_SECS`.
- Nowy rodzaj albumu w menu: `SMART_PL`/`PRIMARY`/`MORE_ORDER` (obok `AlbumRow`).
- Nowy typ telewizora: nowy moduł z klasą o interfejsie jak w §4 i dopisanie go w `_discover_all`.
- Nowy skrót klawiszowy w podglądzie: `Viewer.on_key`; w oknie głównym: `MainWindow._on_key`.

## 10. Kolejność czytania, jeśli chcesz zrozumieć całość

1. `backend.py` od góry do `class ICloud` (funkcje pomocnicze), potem `login`, `iter_assets`, `fetch`, `stream_url`.
2. `app.py:95` `bg()` i `MainWindow.__init__` (1556).
3. `_albums_loaded` → `_on_album_selected` → `load_album` → `_load_more` → `_bind_tile`: pełna droga od kliknięcia
   albumu do miniatury na ekranie.
4. `Viewer` i `ZoomView`.
5. Dopiero potem funkcje dodatkowe (zaznaczanie, TV, skok do daty).


## 4b. Prośby innych aplikacji (0.15.0)

- `--open-album NAZWA`, `--open-date RRRR-MM-DD[..RRRR-MM-DD]` - `parse_open` w `app.py`. Gdy aplikacja już działa,
  nowy proces rejestruje się, wysyła akcję `app.open-album` / `app.open-date` do działającej instancji i kończy się.
  `MainWindow.open_request` czeka, aż wczytają się albumy (`_albums_ready`), potem `_apply_open` zaznacza album
  (rozwija „Moje albumy”) albo wybiera „Wszystkie zdjęcia” i woła `_do_jump`. Nieznany album: jedno odświeżenie
  biblioteki (album mógł właśnie powstać), potem komunikat.
- `bridge.py` - wywołania bez okna (`--albums-json`, `--album-thumbs`, `--range-thumbs`, `--create-album`, `--drive-upload`), opis
  w nagłówku pliku. Zakres dat czyta „Wszystkie zdjęcia” od pierwszego zdjęcia ≥ początek (`iter_jump` rosnąco)
  do pierwszego po końcu. Tworzenie albumu używa `create_album` z pyicloud i `add_to_album` (pomija duplikaty).
- Testy: `tests/scripts/bridge_test.py` i `tests/scripts/drive_bridge_test.py` (udawany ICloud / iCloud Drive, bez sieci) i `tests/scripts/open_test.py` (okno).
