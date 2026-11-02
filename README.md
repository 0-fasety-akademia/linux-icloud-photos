# iCloud Photos (Linux) v0.4.0

Nieoficjalny klient iCloud Photos dla Ubuntu (GTK4 + libadwaita). Zdjęcia zostają
w chmurze: aplikacja pobiera miniatury i podglądy na żądanie, wideo strumieniuje.
Na dysku jest wyłącznie ograniczony cache (do 1 GB).

## Instalacja

1. `sudo apt install ./icloud-photos-linux_0.5.0_all.deb`
   (zależności dociągnie apt; paczka tworzy `/opt/icloud-photos-linux/venv` i instaluje
   tam `pyicloud` - **potrzebny internet**).
2. Uruchom z menu aplikacji: **iCloud Photos (Linux)**. Działa niezależnie od terminala.
3. Pierwsze logowanie: Apple ID, hasło, kod 2FA. Potem loguje się samo.

Aktualizacja: ta sama komenda z nowym plikiem. Usunięcie: `sudo apt remove icloud-photos-linux`.
Jeśli pyicloud się nie zainstalował: `sudo /opt/icloud-photos-linux/venv/bin/pip install pyicloud keyring`.
Diagnostyka: `~/.cache/icloud-photos-linux/debug.log` (wklej fragment przy zgłaszaniu błędów).

## Obsługa

**Lista zdjęć.** Domyślnie od najnowszych; kolejne partie (po 300) doładowują się
podczas przewijania, więc 12 tys. zdjęć nie jest problemem. Przycisk sortowania w nagłówku
odwraca kolejność (zapamiętywane). Aplikacja sprawdza daty pierwszej partii i sama
koryguje albumy, które Apple zwróciło w odwrotnej kolejności.

**Wspomnienia** 
**in progress**
(pierwsza pozycja w menu): aplikacja sama tworzy wspomnienia z dat i lokalizacji
zdjęć - **Wyjazdy** (zdjęcia daleko od miejsca, gdzie zwykle robisz zdjęcia), **Wydarzenia** (kilka
gęstych dni, np. urodziny), **Tego dnia w poprzednich latach**, **Lata** i **Ostatnie tygodnie**; sekcja
**Dla Ciebie** zbiera najświeższe. Karta ma przyciski „Odtwórz” (pokaz slajdów wybranych ~30 zdjęć,
także na TV) i „Zdjęcia” (otwiera zestaw w siatce). Po zalogowaniu aplikacja w tle buduje indeks
biblioteki (tylko ID, daty i współrzędne - **nie zdjęcia**; pierwszy raz może potrwać kilka minut przy
kilkunastu tysiącach zdjęć, potem tylko uzupełnia nowe). Raz dziennie pokaże powiadomienie o nowym
wspomnieniu, a w menu pojawi się „(N nowe)”. Przełącznik „Nazwy miejsc” pobiera nazwy z
OpenStreetMap (wysyła przybliżone współrzędne wyjazdów; domyślnie wyłączony).
Ograniczenie: wspomnienia powstają z dat/GPS/ulubionych - **nie rozpoznają osób ani zwierząt**.

**Układ okna:** separator między menu a siatką można przeciągać (szerokość jest zapamiętywana);
przycisk po lewej w nagłówku chowa/pokazuje menu. Przycisk „siatka” w nagłówku wybiera widok:
małe / standardowe / duże / bardzo duże miniatury (to samo robi suwak).

**Menu albumów** (lewa strona): biblioteka z okładkami, zwijane "Typy mediów" i
"Moje albumy (N)" z miniaturą-okładką (najnowsze zdjęcie albumu), pole szukania.

**Zoom miniatur:** suwak − / + w nagłówku, **Ctrl +**, **Ctrl −**, **Ctrl 0**, Ctrl + kółko.

**Podgląd zdjęcia:** ← →, Home/End; pasek zoomu − suwak + Dopasuj; Ctrl +/−/0, Ctrl+kółko,
szczypanie, dwuklik (1× ↔ 2,5×), przeciąganie; F / F11 pełny ekran; Esc. Przy zoomie > 1,5×
dociągany jest oryginał. Live Photo: przycisk LIVE / L.

**Informacje o zdjęciu:** ikona „i” w nagłówku (ostatnio otwarte lub kliknięte zdjęcie), ikona „i”
i klawisz **I** w podglądzie, albo prawy przycisk myszy → Informacje: nazwa pliku, data wykonania,
rozmiar, wymiary, lokalizacja (współrzędne + mapa; nazwa miejsca tylko na żądanie) oraz telefon/aparat
z EXIF (jeśli podgląd z iCloud ich nie zawiera - przycisk „Wczytaj z oryginału”).
**Prawy przycisk myszy** (siatka i podgląd): Informacje, Odtwórz w mpv, Wyślij na TV,
Zapisz oryginał jako…, Kopiuj nazwę pliku.

**Live Photos:** przycisk LIVE, klawisz L/Spacja albo przytrzymanie zdjęcia. Krótki klip jest pobierany
do cache i odtwarzany lokalnie; jeśli wbudowany odtwarzacz nie ruszy, otwiera się w mpv.

**Filmy:** miniatura z klatką filmu; kliknięcie otwiera film w osobnym oknie **mpv**.
W podglądzie film ma plakat z przyciskiem ▶ (Spacja/Enter). Gdy mpv zgłosi błąd, pojawia się
komunikat z jego treścią. Wbudowany odtwarzacz: `ICLOUD_PHOTOS_EMBEDDED_VIDEO=1`.

**Pokaz slajdów:** niebieski przycisk PLAY w nagłówku (bieżący album), pełny ekran,
przenikanie, Spacja = pauza, ← →, odstęp 3/5/8/15 s, Esc. Filmy są pomijane.

**Wysyłanie na TV:** przycisk z ikoną monitora w nagłówku → lista urządzeń w sieci (DLNA/UPnP:
m.in. LG, Samsung, Sony; oraz Chromecast / TV z Google Cast) → wybierz. Potem otwarte zdjęcie lub
pokaz slajdów pojawia się też na TV. **AirPlay (Apple TV) jeszcze nie jest obsługiwany.** Komputer i TV muszą być w jednej sieci, a zapora (ufw)
nie może blokować połączeń przychodzących z TV.

**Wysyłanie do iCloud:** przeciągnij pliki (JPG, PNG, HEIC, GIF, TIFF, DNG, MOV, MP4)
do okna albo kliknij **+**; wybierz album docelowy (domyślnie bieżący) i "Prześlij".

## Ograniczenia

- Advanced Data Protection musi być wyłączone (inaczej web/API nie działa).
- Sesja 2FA wygasa co kilka tygodni; API jest nieoficjalne (pyicloud) i Apple może je zmienić.
- Okładki albumów są zapamiętywane na dysku i nie odświeżają się same.
- Konta ze starszą weryfikacją 2SA nie są obsługiwane.
