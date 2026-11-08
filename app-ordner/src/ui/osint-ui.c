/* osint-ui: Oberflaeche von FlipperOne-OSINT (SDL2, 256x144, wie die TestApp).
 * Aufruf: osint-ui <pfad-zu-osint-cli>
 * Bedienung: Tastatur (Hoch/Runter, Enter, Esc, Text tippen, Strg+V) und Maus.
 */
#define _GNU_SOURCE
#include <SDL.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

#define W 256
#define H 144
#define CW 6
#define CH 8
#define COLS (W / CW) /* 42 */
#define ROWS (H / CH) /* 18 */
#define VH 15         /* sichtbare Ergebniszeilen (Zeilen 1..15) */
#define TABH 13       /* Hoehe der Tasten-Leiste unten */
#define MAXLINES 4000
#define MAXIN 120
#define NMODES 8

#ifndef APP_VERSION
#define APP_VERSION "dev"
#endif

typedef struct { Uint8 r, g, b; } Color;
/* Orange-Stil wie die Flipper-Apps (z.B. nmap) */
static const Color C_BG = {240, 138, 36};    /* Hintergrund */
static const Color C_INK = {34, 17, 0};      /* Text / Rahmen */
static const Color C_PANEL = {251, 166, 68}; /* Felder / Tasten */
static const Color C_DARK = {196, 98, 4};    /* Abschnittsbalken */
static const Color C_SOFT = {120, 58, 0};    /* Nebentext */
static const Color C_LIGHT = {255, 176, 80}; /* Schrift auf Schwarz */

/* ---------- 5x7-Schrift ---------- */
typedef struct { char c; const char *r[7]; } Glyph;
static const Glyph glyphs[] = {
    {' ', {".....", ".....", ".....", ".....", ".....", ".....", "....."}},
    {'!', {"..X..", "..X..", "..X..", "..X..", "..X..", ".....", "..X.."}},
    {'"', {".X.X.", ".X.X.", ".....", ".....", ".....", ".....", "....."}},
    {'#', {".X.X.", ".X.X.", "XXXXX", ".X.X.", "XXXXX", ".X.X.", ".X.X."}},
    {'$', {"..X..", ".XXXX", "X.X..", ".XXX.", "..X.X", "XXXX.", "..X.."}},
    {'%', {"XX...", "XX..X", "...X.", "..X..", ".X...", "X..XX", "...XX"}},
    {'&', {".XX..", "X..X.", "X.X..", ".X...", "X.X.X", "X..X.", ".XX.X"}},
    {'\'', {"..X..", "..X..", ".....", ".....", ".....", ".....", "....."}},
    {'(', {"...X.", "..X..", ".X...", ".X...", ".X...", "..X..", "...X."}},
    {')', {".X...", "..X..", "...X.", "...X.", "...X.", "..X..", ".X..."}},
    {'*', {".....", "..X..", "X.X.X", ".XXX.", "X.X.X", "..X..", "....."}},
    {'+', {".....", "..X..", "..X..", "XXXXX", "..X..", "..X..", "....."}},
    {',', {".....", ".....", ".....", ".....", "..XX.", "...X.", "..X.."}},
    {'-', {".....", ".....", ".....", "XXXXX", ".....", ".....", "....."}},
    {'.', {".....", ".....", ".....", ".....", ".....", ".XX..", ".XX.."}},
    {'/', {"....X", "....X", "...X.", "..X..", ".X...", "X....", "X...."}},
    {'0', {".XXX.", "X...X", "X..XX", "X.X.X", "XX..X", "X...X", ".XXX."}},
    {'1', {"..X..", ".XX..", "..X..", "..X..", "..X..", "..X..", ".XXX."}},
    {'2', {".XXX.", "X...X", "....X", "...X.", "..X..", ".X...", "XXXXX"}},
    {'3', {"XXXXX", "...X.", "..X..", "...X.", "....X", "X...X", ".XXX."}},
    {'4', {"...X.", "..XX.", ".X.X.", "X..X.", "XXXXX", "...X.", "...X."}},
    {'5', {"XXXXX", "X....", "XXXX.", "....X", "....X", "X...X", ".XXX."}},
    {'6', {"..XX.", ".X...", "X....", "XXXX.", "X...X", "X...X", ".XXX."}},
    {'7', {"XXXXX", "....X", "...X.", "..X..", ".X...", ".X...", ".X..."}},
    {'8', {".XXX.", "X...X", "X...X", ".XXX.", "X...X", "X...X", ".XXX."}},
    {'9', {".XXX.", "X...X", "X...X", ".XXXX", "....X", "...X.", ".XX.."}},
    {':', {".....", ".XX..", ".XX..", ".....", ".XX..", ".XX..", "....."}},
    {';', {".....", ".XX..", ".XX..", ".....", ".XX..", "..X..", ".X..."}},
    {'<', {"...X.", "..X..", ".X...", "X....", ".X...", "..X..", "...X."}},
    {'=', {".....", ".....", "XXXXX", ".....", "XXXXX", ".....", "....."}},
    {'>', {".X...", "..X..", "...X.", "....X", "...X.", "..X..", ".X..."}},
    {'?', {".XXX.", "X...X", "....X", "...X.", "..X..", ".....", "..X.."}},
    {'@', {".XXX.", "X...X", "X.XXX", "X.X.X", "X.XX.", "X....", ".XXX."}},
    {'A', {".XXX.", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"}},
    {'B', {"XXXX.", "X...X", "X...X", "XXXX.", "X...X", "X...X", "XXXX."}},
    {'C', {".XXX.", "X...X", "X....", "X....", "X....", "X...X", ".XXX."}},
    {'D', {"XXXX.", "X...X", "X...X", "X...X", "X...X", "X...X", "XXXX."}},
    {'E', {"XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "XXXXX"}},
    {'F', {"XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "X...."}},
    {'G', {".XXX.", "X...X", "X....", "X.XXX", "X...X", "X...X", ".XXXX"}},
    {'H', {"X...X", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"}},
    {'I', {".XXX.", "..X..", "..X..", "..X..", "..X..", "..X..", ".XXX."}},
    {'J', {"..XXX", "...X.", "...X.", "...X.", "...X.", "X..X.", ".XX.."}},
    {'K', {"X...X", "X..X.", "X.X..", "XX...", "X.X..", "X..X.", "X...X"}},
    {'L', {"X....", "X....", "X....", "X....", "X....", "X....", "XXXXX"}},
    {'M', {"X...X", "XX.XX", "X.X.X", "X.X.X", "X...X", "X...X", "X...X"}},
    {'N', {"X...X", "XX..X", "X.X.X", "X..XX", "X...X", "X...X", "X...X"}},
    {'O', {".XXX.", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."}},
    {'P', {"XXXX.", "X...X", "X...X", "XXXX.", "X....", "X....", "X...."}},
    {'Q', {".XXX.", "X...X", "X...X", "X...X", "X.X.X", "X..X.", ".XX.X"}},
    {'R', {"XXXX.", "X...X", "X...X", "XXXX.", "X.X..", "X..X.", "X...X"}},
    {'S', {".XXXX", "X....", "X....", ".XXX.", "....X", "....X", "XXXX."}},
    {'T', {"XXXXX", "..X..", "..X..", "..X..", "..X..", "..X..", "..X.."}},
    {'U', {"X...X", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."}},
    {'V', {"X...X", "X...X", "X...X", "X...X", "X...X", ".X.X.", "..X.."}},
    {'W', {"X...X", "X...X", "X...X", "X.X.X", "X.X.X", "XX.XX", "X...X"}},
    {'X', {"X...X", "X...X", ".X.X.", "..X..", ".X.X.", "X...X", "X...X"}},
    {'Y', {"X...X", "X...X", ".X.X.", "..X..", "..X..", "..X..", "..X.."}},
    {'Z', {"XXXXX", "....X", "...X.", "..X..", ".X...", "X....", "XXXXX"}},
    {'[', {".XXX.", ".X...", ".X...", ".X...", ".X...", ".X...", ".XXX."}},
    {'\\', {"X....", "X....", ".X...", "..X..", "...X.", "....X", "....X"}},
    {']', {".XXX.", "...X.", "...X.", "...X.", "...X.", "...X.", ".XXX."}},
    {'^', {"..X..", ".X.X.", "X...X", ".....", ".....", ".....", "....."}},
    {'_', {".....", ".....", ".....", ".....", ".....", ".....", "XXXXX"}},
    {'`', {".X...", "..X..", ".....", ".....", ".....", ".....", "....."}},
    {'{', {"..XX.", ".X...", ".X...", "X....", ".X...", ".X...", "..XX."}},
    {'|', {"..X..", "..X..", "..X..", "..X..", "..X..", "..X..", "..X.."}},
    {'}', {".XX..", "...X.", "...X.", "....X", "...X.", "...X.", ".XX.."}},
    {'~', {".....", ".....", ".X...", "X.X.X", "...X.", ".....", "....."}},
};

/* ---------- Zustand ---------- */
typedef struct {
    const char *label, *cmd, *prompt, *example, *d1, *d2;
} Mode;

static const Mode modes[NMODES] = {
    {"USERNAME", "username", "USERNAME", "BEISPIEL: MAXMUSTER",
     "PRUEFT, OB DER NAME AUF UEBER 30", "OEFFENTLICHEN PLATTFORMEN VERGEBEN IST."},
    {"E-MAIL-ADRESSE", "email", "E-MAIL-ADRESSE", "BEISPIEL: NAME@BEISPIEL.DE",
     "SYNTAX, MAILSERVER, SPF/DMARC,", "GRAVATAR, ANBIETER, DOMAIN-DATEN."},
    {"TELEFONNUMMER", "phone", "TELEFONNUMMER", "BEISPIEL: +49 171 1234567",
     "LAND, FORMAT UND LEITUNGSART", "(OFFLINE). KEINE HALTERABFRAGE."},
    {"DOMAIN / WEBSEITE", "domain", "DOMAIN", "BEISPIEL: BEISPIEL.DE",
     "DNS, REGISTRAR, WEBSERVER, TLS, HEADER", "UND SUBDOMAINS (ZERTIFIKATS-LOGS)."},
    {"IP-ADRESSE", "ip", "IP-ADRESSE", "BEISPIEL: 8.8.8.8",
     "RDNS, BETREIBER, LAND, OFFENE PORTS", "UND BEKANNTE SCHWACHSTELLEN."},
    {"NAME -> USERNAMES", "name", "VOR- UND NACHNAME", "BEISPIEL: MAX MUSTERMANN",
     "ERZEUGT USERNAME-VARIANTEN AUS EINEM", "NAMEN (NUR TEXT, KEINE SUCHE)."},
    {"HILFE / INFO", NULL, NULL, NULL, "BEDIENUNG UND HINWEISE.", ""},
    {"TASTEN-TEST", NULL, NULL, NULL, "ZEIGT DIE CODES DER FLIPPER-TASTEN", "(X, MENUE, OK ...) UND DES TOUCHS."},
};

enum { S_MENU, S_INPUT, S_RUN, S_HELP, S_KEYS };
static int screen = S_MENU;
static int sel = 0;
static int mode_idx = 0;
static char inputs[NMODES][MAXIN + 1];
static int quit = 0;
static int text_seen = 0;

typedef struct { char t[COLS + 1]; unsigned char kind; } Line;
static Line lines[MAXLINES];
static int nlines = 0, scroll_pos = 0, follow = 1;

static pid_t child = -1;
static int child_fd = -1;
static int running = 0, finished = 0, got_output = 0;
static char inbuf[4096];
static int inlen = 0;
static const char *cli_path = "osint-cli";

#define NKEYLOG 9
static char keylog[NKEYLOG][44];
static int keylog_n = 0, esc_streak = 0;
static int drag_active = 0, drag_last_y = 0, drag_acc = 0;

static void log_event(const char *fmt, int a, int b, const char *name) {
    for (int i = NKEYLOG - 1; i > 0; i--) memcpy(keylog[i], keylog[i - 1], sizeof keylog[0]);
    snprintf(keylog[0], sizeof keylog[0], fmt, name, a, b);
    if (keylog_n < NKEYLOG) keylog_n++;
    fprintf(stderr, "%s\n", keylog[0]);
}

static SDL_Window *win;
static SDL_Renderer *ren;
static SDL_Texture *atlas;

/* ---------- Zeichnen ---------- */
static void build_atlas(void) {
    static Uint32 px[96 * 48];
    memset(px, 0, sizeof px);
    for (size_t g = 0; g < sizeof glyphs / sizeof glyphs[0]; g++) {
        int idx = glyphs[g].c - 32;
        int gx = (idx % 16) * CW, gy = (idx / 16) * CH;
        for (int y = 0; y < 7; y++)
            for (int x = 0; x < 5; x++)
                if (glyphs[g].r[y][x] == 'X') px[(gy + y) * 96 + gx + x] = 0xFFFFFFFFu;
    }
    atlas = SDL_CreateTexture(ren, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, 96, 48);
    if (atlas) {
        SDL_UpdateTexture(atlas, NULL, px, 96 * 4);
        SDL_SetTextureBlendMode(atlas, SDL_BLENDMODE_BLEND);
    }
}

static void rect(int x, int y, int w, int h, Color c) {
    SDL_SetRenderDrawColor(ren, c.r, c.g, c.b, 255);
    SDL_Rect rc = {x, y, w, h};
    SDL_RenderFillRect(ren, &rc);
}


static void put_char(int x, int y, char c, Color col) {
    if (c >= 'a' && c <= 'z') c = (char)(c - 32);
    if (c < 32 || c > 126) c = '?';
    int idx = c - 32;
    SDL_Rect s = {(idx % 16) * CW, (idx / 16) * CH, CW, CH};
    SDL_Rect d = {x, y, CW, CH};
    SDL_SetTextureColorMod(atlas, col.r, col.g, col.b);
    SDL_RenderCopy(ren, atlas, &s, &d);
}

static void text_px(int x, int y, const char *s, Color c) {
    for (int i = 0; s[i] && x + i * CW < W; i++) put_char(x + i * CW, y, s[i], c);
}

static void icon(int x, int y) { /* kleine Lupe */
    rect(x, y, 5, 1, C_INK);
    rect(x, y + 4, 5, 1, C_INK);
    rect(x, y, 1, 5, C_INK);
    rect(x + 4, y, 1, 5, C_INK);
    rect(x + 5, y + 5, 2, 2, C_INK);
}

static void title(const char *left, const char *right) {
    icon(3, 0);
    text_px(14, 0, left, C_INK);
    text_px(15, 0, left, C_INK); /* fett */
    int rl = (int)strlen(right);
    text_px(W - 4 - rl * CW, 0, right, C_INK);
    rect(0, CH - 1, W, 1, C_INK);
}

static void tab(int x, const char *s, int primary) {
    if (!s || !*s) return;
    int w = 80, y = H - TABH;
    rect(x, y, w, TABH, C_INK);
    rect(x + 1, y + 1, w - 2, TABH - 1, primary ? C_INK : C_PANEL);
    rect(x, y, 1, 1, C_BG); /* runde Ecken oben */
    rect(x + w - 1, y, 1, 1, C_BG);
    int tw = (int)strlen(s) * CW;
    text_px(x + (w - tw) / 2, y + 3, s, primary ? C_LIGHT : C_INK);
}

static void softkeys(const char *l, const char *m, const char *r) {
    tab(2, l, 0);
    tab(88, m, 0);
    tab(174, r, 1);
}

/* ---------- Ergebniszeilen ---------- */
static void add_line(const char *s, int kind) {
    if (nlines >= MAXLINES) return;
    strncpy(lines[nlines].t, s, COLS);
    lines[nlines].t[COLS] = 0;
    lines[nlines].kind = (unsigned char)kind;
    nlines++;
    if (follow) scroll_pos = nlines > VH ? nlines - VH : 0;
}

static void wrap_add(char m, const char *s, int kind) {
    const int width = COLS - 2;
    int first = 1;
    const char *p = s;
    for (;;) {
        int len = (int)strlen(p);
        int n = len > width ? width : len;
        int brk = n;
        if (len > width) {
            int sp = -1;
            for (int i = n; i > 0; i--)
                if (p[i] == ' ') { sp = i; break; }
            if (sp >= 8) brk = sp;
        }
        char buf[COLS + 1];
        buf[0] = first ? m : ' ';
        buf[1] = ' ';
        memcpy(buf + 2, p, (size_t)brk);
        buf[2 + brk] = 0;
        add_line(buf, kind);
        p += brk;
        while (*p == ' ') p++;
        first = 0;
        if (!*p) break;
    }
}

static void push_result(const char *raw) {
    char m = raw[0];
    const char *rest = raw[0] ? (raw[1] == ' ' ? raw + 2 : raw + 1) : raw;
    got_output = 1;
    switch (m) {
    case '#':
        if (nlines > 0) add_line("", 0);
        wrap_add('#', rest, 4);
        break;
    case '+': wrap_add('+', rest, 1); break;
    case '-': wrap_add('-', rest, 2); break;
    case '!': wrap_add('!', rest, 3); break;
    case 'i': wrap_add(' ', rest, 0); break;
    default: wrap_add(' ', raw, 0); break;
    }
}

/* ---------- Hilfsprogramm starten / auslesen ---------- */
static void stop_child(void) {
    if (child > 0) {
        kill(child, SIGTERM);
        waitpid(child, NULL, 0);
        child = -1;
    }
    if (child_fd >= 0) {
        close(child_fd);
        child_fd = -1;
    }
    running = 0;
}

static int spawn_cli(const char *type, const char *value) {
    int p[2];
    if (pipe(p) != 0) return -1;
    pid_t pid = fork();
    if (pid < 0) {
        close(p[0]);
        close(p[1]);
        return -1;
    }
    if (pid == 0) {
        signal(SIGPIPE, SIG_DFL);
        dup2(p[1], 1);
        dup2(p[1], 2);
        close(p[0]);
        close(p[1]);
        execl(cli_path, cli_path, type, value, (char *)NULL);
        _exit(127);
    }
    close(p[1]);
    fcntl(p[0], F_SETFL, O_NONBLOCK);
    child = pid;
    child_fd = p[0];
    return 0;
}

static void flush_inbuf_line(int upto) {
    char line[COLS * 8];
    int n = upto < (int)sizeof line - 1 ? upto : (int)sizeof line - 1;
    memcpy(line, inbuf, (size_t)n);
    line[n] = 0;
    while (n > 0 && (line[n - 1] == '\r' || line[n - 1] == ' ')) line[--n] = 0;
    if (n > 0) push_result(line);
}

static void pump(void) {
    if (!running) return;
    for (;;) {
        ssize_t n = read(child_fd, inbuf + inlen, sizeof inbuf - (size_t)inlen - 1);
        if (n > 0) {
            inlen += (int)n;
            for (;;) {
                char *nl = memchr(inbuf, '\n', (size_t)inlen);
                int full = (inlen >= (int)sizeof inbuf - 1);
                if (!nl && !full) break;
                int upto = nl ? (int)(nl - inbuf) : inlen;
                flush_inbuf_line(upto);
                int consumed = nl ? upto + 1 : upto;
                memmove(inbuf, inbuf + consumed, (size_t)(inlen - consumed));
                inlen -= consumed;
            }
            continue;
        }
        if (n < 0 && errno == EINTR) continue;
        if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return;
        /* EOF oder Fehler */
        if (inlen > 0) flush_inbuf_line(inlen);
        inlen = 0;
        int status = 0;
        if (child > 0) {
            waitpid(child, &status, 0);
            child = -1;
        }
        close(child_fd);
        child_fd = -1;
        running = 0;
        finished = 1;
        if (!got_output) {
            if (WIFEXITED(status) && WEXITSTATUS(status) == 127)
                push_result("! BACKEND (OSINT-CLI) NICHT GEFUNDEN");
            else
                push_result("! KEINE AUSGABE VOM BACKEND");
        } else if (WIFEXITED(status) && WEXITSTATUS(status) != 0) {
            char b[64];
            snprintf(b, sizeof b, "! BACKEND BEENDET MIT CODE %d", WEXITSTATUS(status));
            push_result(b);
        }
        return;
    }
}

static void start_run(void) {
    char *in = inputs[mode_idx];
    size_t l = strlen(in);
    while (l > 0 && in[l - 1] == ' ') in[--l] = 0;
    if (l == 0) return;
    stop_child();
    nlines = 0;
    scroll_pos = 0;
    follow = 1;
    inlen = 0;
    finished = 0;
    got_output = 0;
    screen = S_RUN;
    if (spawn_cli(modes[mode_idx].cmd, in) != 0) {
        push_result("! BACKEND KONNTE NICHT GESTARTET WERDEN");
        finished = 1;
    } else {
        running = 1;
    }
}

/* ---------- Eingabe ---------- */
static void activate(int idx) {
    if (idx == NMODES - 2) {
        screen = S_HELP;
    } else if (idx == NMODES - 1) {
        screen = S_KEYS;
        esc_streak = 0;
    } else {
        mode_idx = idx;
        screen = S_INPUT;
        SDL_StartTextInput();
    }
}

static void append_input(const char *s) {
    char *in = inputs[mode_idx];
    size_t l = strlen(in);
    for (; *s && l < MAXIN; s++)
        if ((unsigned char)*s >= 32 && (unsigned char)*s <= 126) in[l++] = *s;
    in[l] = 0;
}

static char key_char(SDL_Keycode s, Uint16 mod) {
    int sh = (mod & KMOD_SHIFT) != 0;
    if (s >= 'a' && s <= 'z') return (char)((sh ^ ((mod & KMOD_CAPS) != 0)) ? s - 32 : s);
    if (!sh) return (s >= 32 && s <= 126) ? (char)s : 0;
    switch (s) {
    case '1': return '!'; case '2': return '@'; case '3': return '#'; case '4': return '$';
    case '5': return '%'; case '6': return '^'; case '7': return '&'; case '8': return '*';
    case '9': return '('; case '0': return ')'; case '-': return '_'; case '=': return '+';
    case '[': return '{'; case ']': return '}'; case '\\': return '|'; case ';': return ':';
    case '\'': return '"'; case ',': return '<'; case '.': return '>'; case '/': return '?';
    case '`': return '~';
    }
    return (s >= 32 && s <= 126) ? (char)s : 0;
}

static void scroll_by(int d) {
    int max = nlines > VH ? nlines - VH : 0;
    scroll_pos += d;
    if (scroll_pos < 0) scroll_pos = 0;
    if (scroll_pos > max) scroll_pos = max;
    follow = (scroll_pos >= max);
}

static void go_back_from_run(void) {
    stop_child();
    screen = S_INPUT;
}

static void softkey(int n);

static void on_key(const SDL_KeyboardEvent *k, char *kbuf) {
    SDL_Keycode s = k->keysym.sym;
    Uint16 mod = k->keysym.mod;
    int enter = (s == SDLK_RETURN || s == SDLK_KP_ENTER);
    log_event("TASTE %s SYM=%X SC=%d", (int)s, (int)k->keysym.scancode, SDL_GetKeyName(s));
    if (screen == S_KEYS) {
        if (s == SDLK_ESCAPE || s == SDLK_BACKSPACE || s == SDLK_AC_BACK || s == SDLK_CANCEL) {
            if (++esc_streak >= 3) screen = S_MENU;
        } else {
            esc_streak = 0;
        }
        return;
    }
    /* Flipper-Tasten: X = zurueck, Menue = Hilfe/Neu/Einfuegen, Haken = OK */
    if (s == SDLK_AC_BACK || s == SDLK_CANCEL) { softkey(0); return; }
    if (s == SDLK_MENU || s == SDLK_APPLICATION) { softkey(1); return; }
    if (s == SDLK_SELECT || s == SDLK_EXECUTE) { softkey(2); return; }
    if (screen == S_RUN && (s == SDLK_F4 || s == SDLK_PRINTSCREEN || s == SDLK_TAB || s == SDLK_SPACE)) { softkey(2); return; }
    if (s == SDLK_F1) { softkey(0); return; }
    if (s == SDLK_F2) { softkey(1); return; }
    if (s == SDLK_F3) { softkey(2); return; }
    switch (screen) {
    case S_MENU:
        if (s == SDLK_UP) sel = (sel + NMODES - 1) % NMODES;
        else if (s == SDLK_DOWN) sel = (sel + 1) % NMODES;
        else if (enter) activate(sel);
        else if (s >= SDLK_1 && s <= SDLK_8) { sel = (int)(s - SDLK_1); activate(sel); }
        else if (s == SDLK_ESCAPE) quit = 1;
        break;
    case S_INPUT:
        if (s == SDLK_ESCAPE) screen = S_MENU;
        else if (enter) start_run();
        else if (s == SDLK_BACKSPACE) {
            size_t l = strlen(inputs[mode_idx]);
            if (l > 0) inputs[mode_idx][l - 1] = 0;
        } else if (s == 'v' && (mod & KMOD_CTRL)) {
            char *cb = SDL_GetClipboardText();
            if (cb) { append_input(cb); SDL_free(cb); }
        } else if (!(mod & (KMOD_CTRL | KMOD_ALT | KMOD_GUI))) {
            char c = key_char(s, mod);
            size_t l = strlen(kbuf);
            if (c && l < 14) { kbuf[l] = c; kbuf[l + 1] = 0; }
        }
        break;
    case S_RUN:
        if (s == SDLK_ESCAPE) go_back_from_run();
        else if (s == SDLK_UP) scroll_by(-1);
        else if (s == SDLK_DOWN) scroll_by(1);
        else if (s == SDLK_PAGEUP) scroll_by(-(VH - 1));
        else if (s == SDLK_PAGEDOWN) scroll_by(VH - 1);
        else if (s == SDLK_HOME) scroll_by(-MAXLINES);
        else if (s == SDLK_END) scroll_by(MAXLINES);
        else if (enter && finished) start_run();
        break;
    case S_HELP:
        if (s == SDLK_ESCAPE || enter) screen = S_MENU;
        break;
    case S_KEYS:
        break;
    }
}

#define MENU_Y0 13
#define MENU_P 10

static void softkey(int n) {
    switch (screen) {
    case S_MENU:
        if (n == 0) quit = 1;
        else if (n == 1) screen = S_HELP;
        else activate(sel);
        break;
    case S_INPUT:
        if (n == 0) screen = S_MENU;
        else if (n == 1) {
            char *cb = SDL_GetClipboardText();
            if (cb) { append_input(cb); SDL_free(cb); }
        } else start_run();
        break;
    case S_RUN:
        if (n == 0) go_back_from_run();
        else if (n == 1) { if (finished) start_run(); }
        else {
            int max = nlines > VH ? nlines - VH : 0;
            if (scroll_pos >= max) scroll_by(-MAXLINES);
            else scroll_by(VH - 1);
        }
        break;
    case S_HELP:
        screen = S_MENU;
        break;
    case S_KEYS:
        if (n == 0) screen = S_MENU;
        break;
    }
}

static void on_click(int px, int py) {
    int ww = W, wh = H;
    SDL_GetWindowSize(win, &ww, &wh);
    if (ww <= 0 || wh <= 0) return;
    int x = px * W / ww, y = py * H / wh;
    log_event("%s X=%d Y=%d", x, y, "KLICK");
    if (screen == S_KEYS) {
        if (y >= H - TABH && x < 86) screen = S_MENU;
        return;
    }
    if (y >= H - TABH) {
        softkey(x < 86 ? 0 : (x < 172 ? 1 : 2));
        return;
    }
    if (screen == S_MENU) {
        int i = (y - MENU_Y0) / MENU_P;
        if (y >= MENU_Y0 && i >= 0 && i < NMODES) { sel = i; activate(sel); }
    } else if (screen == S_HELP) {
        screen = S_MENU;
    }
}

static void on_drag(int py, int down) {
    int wh = H, ww = W;
    SDL_GetWindowSize(win, &ww, &wh);
    if (wh <= 0) return;
    int y = py * H / wh;
    if (down) { drag_active = 1; drag_last_y = y; drag_acc = 0; return; }
    if (!drag_active || screen != S_RUN) return;
    drag_acc += drag_last_y - y;
    drag_last_y = y;
    while (drag_acc >= CH) { scroll_by(1); drag_acc -= CH; }
    while (drag_acc <= -CH) { scroll_by(-1); drag_acc += CH; }
}

static void on_wheel(int dy) {
    if (screen == S_RUN) scroll_by(-dy * 3);
    else if (screen == S_MENU) sel = (sel - dy + NMODES * 8) % NMODES;
}

/* ---------- Bildschirme ---------- */
static void draw_menu(void) {
    title("OSINT", "V" APP_VERSION);
    for (int i = 0; i < NMODES; i++) {
        int y = MENU_Y0 + i * MENU_P;
        char b[COLS + 1];
        snprintf(b, sizeof b, "%d  %s", i + 1, modes[i].label);
        rect(4, y - 1, W - 8, 10, C_INK);
        if (i == sel) {
            text_px(10, y, b, C_LIGHT);
        } else {
            rect(5, y, W - 10, 8, C_PANEL);
            text_px(10, y, b, C_INK);
        }
    }
    text_px(4, 99, modes[sel].d1, C_SOFT);
    text_px(4, 108, modes[sel].d2, C_SOFT);
    softkeys("ENDE", "HILFE", "OEFFNEN");
}

static void draw_input(void) {
    const Mode *m = &modes[mode_idx];
    char t[COLS + 1];
    snprintf(t, sizeof t, "%s", m->prompt);
    title("OSINT", t);
    text_px(4, 16, m->prompt, C_INK);
    rect(4, 27, W - 8, 14, C_INK);
    rect(5, 28, W - 10, 12, C_PANEL);
    const char *in = inputs[mode_idx];
    int l = (int)strlen(in);
    int vis = (W - 24) / CW;
    const char *shown = l > vis ? in + (l - vis) : in;
    text_px(10, 31, shown, C_INK);
    int cx = 10 + (int)strlen(shown) * CW;
    if ((SDL_GetTicks() / 500) % 2 == 0 && cx < W - 8) put_char(cx, 31, '_', C_INK);
    text_px(4, 48, m->example, C_SOFT);
    text_px(4, 72, "NUR FUER EIGENE DATEN ODER MIT", C_SOFT);
    text_px(4, 81, "EINWILLIGUNG DER BETROFFENEN NUTZEN.", C_SOFT);
    softkeys("ZURUECK", "EINFUEGEN", "START");
}

static void draw_run(void) {
    const Mode *m = &modes[mode_idx];
    static const char spin[] = "|/-\\";
    char right[24];
    if (running) snprintf(right, sizeof right, "%c LAEUFT", spin[(SDL_GetTicks() / 120) % 4]);
    else snprintf(right, sizeof right, "FERTIG");
    (void)m;
    title("OSINT", right);
    static const Color kc[5] = {{34, 17, 0}, {0, 84, 22}, {128, 64, 0}, {150, 18, 0}, {34, 17, 0}};
    for (int r = 0; r < VH; r++) {
        int i = scroll_pos + r;
        if (i >= nlines) break;
        int y = (1 + r) * CH + 1;
        if (lines[i].kind % 5 == 4) rect(0, y - 1, W - 4, CH, C_DARK);
        text_px(1, y, lines[i].t, kc[lines[i].kind % 5]);
    }
    if (nlines > VH) {
        int track = VH * CH;
        int th = track * VH / nlines;
        if (th < 6) th = 6;
        int max = nlines - VH;
        int ty = CH + (track - th) * scroll_pos / (max > 0 ? max : 1);
        rect(W - 3, CH, 2, track, C_DARK);
        rect(W - 3, ty, 2, th, C_INK);
    }
    if (running) softkeys("STOP", NULL, "SEITE");
    else softkeys("ZURUECK", "NEU", "SEITE");
}

static void draw_help(void) {
    title("HILFE / INFO", "V" APP_VERSION);
    static const char *h[] = {
        "ALLROUNDER FUER OEFFENTLICHE INFOS:",
        "USERNAME, E-MAIL, TELEFON, DOMAIN, IP.",
        "",
        "FLIPPER-TASTEN: X = ZURUECK, MENUE = HILFE,",
        "HAKEN = OK. PFEILE, ENTER, ESC, F1-F3 UND",
        "TOUCH/MAUS (WISCHEN = SCROLLEN) GEHEN AUCH.",
        "",
        "WICHTIG: NUR FUER EIGENE DATEN ODER",
        "MIT EINWILLIGUNG DER BETROFFENEN.",
        "KEINE PERSONENSUCHE, KEINE HALTERABFRAGE.",
    };
    static const Color red = {150, 18, 0};
    for (size_t i = 0; i < sizeof h / sizeof h[0]; i++)
        text_px(4, 14 + (int)i * 10, h[i], i >= 7 ? red : C_INK);
    softkeys(NULL, NULL, "ZURUECK");
}

static void draw_keys(void) {
    title("TASTEN-TEST", "");
    text_px(4, 12, "DRUECKE TASTEN / TIPPE AUF DEN SCHIRM:", C_INK);
    for (int i = 0; i < keylog_n; i++) text_px(4, 24 + i * 10, keylog[i], i == 0 ? C_INK : C_SOFT);
    text_px(4, 116, "3X X-TASTE = ZURUECK", C_SOFT);
    softkeys("ZURUECK", NULL, NULL);
}

static void render(void) {
    SDL_SetRenderDrawColor(ren, C_BG.r, C_BG.g, C_BG.b, 255);
    SDL_RenderClear(ren);
    switch (screen) {
    case S_MENU: draw_menu(); break;
    case S_INPUT: draw_input(); break;
    case S_RUN: draw_run(); break;
    case S_HELP: draw_help(); break;
    case S_KEYS: draw_keys(); break;
    }
    SDL_RenderPresent(ren);
}

int main(int argc, char **argv) {
    if (argc > 1) cli_path = argv[1];
    signal(SIGPIPE, SIG_IGN);

    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
        return 1;
    }
    win = SDL_CreateWindow("OSINT", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, W, H, SDL_WINDOW_SHOWN);
    if (!win) {
        fprintf(stderr, "SDL_CreateWindow: %s\n", SDL_GetError());
        return 1;
    }
    ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_SOFTWARE);
    if (!ren) {
        fprintf(stderr, "SDL_CreateRenderer: %s\n", SDL_GetError());
        return 1;
    }
    SDL_RenderSetLogicalSize(ren, W, H);
    build_atlas();
    if (!atlas) {
        fprintf(stderr, "Textur: %s\n", SDL_GetError());
        return 1;
    }
    fprintf(stderr, "osint-ui %s: SDL-Treiber %s\n", APP_VERSION, SDL_GetCurrentVideoDriver() ? SDL_GetCurrentVideoDriver() : "?");

    while (!quit) {
        SDL_Event e;
        char tbuf[64] = {0}, kbuf[16] = {0};
        while (SDL_PollEvent(&e)) {
            switch (e.type) {
            case SDL_QUIT: quit = 1; break;
            case SDL_TEXTINPUT:
                strncat(tbuf, e.text.text, sizeof tbuf - strlen(tbuf) - 1);
                break;
            case SDL_MOUSEWHEEL: on_wheel(e.wheel.y); break;
            case SDL_MOUSEBUTTONDOWN:
                if (e.button.button == SDL_BUTTON_LEFT) { on_drag(e.button.y, 1); on_click(e.button.x, e.button.y); }
                break;
            case SDL_MOUSEMOTION:
                if (e.motion.state & SDL_BUTTON_LMASK) on_drag(e.motion.y, 0);
                break;
            case SDL_MOUSEBUTTONUP: drag_active = 0; break;
            case SDL_KEYDOWN: on_key(&e.key, kbuf); break;
            default: break;
            }
        }
        if (screen == S_INPUT) {
            if (tbuf[0]) { append_input(tbuf); text_seen = 1; }
            else if (!text_seen && kbuf[0]) append_input(kbuf);
        } else if (tbuf[0]) {
            text_seen = 1;
        }
        pump();
        render();
        SDL_Delay(40);
    }
    stop_child();
    SDL_DestroyTexture(atlas);
    SDL_DestroyRenderer(ren);
    SDL_DestroyWindow(win);
    SDL_Quit();
    return 0;
}
