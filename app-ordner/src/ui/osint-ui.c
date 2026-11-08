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
#define VH 16         /* sichtbare Ergebniszeilen (Zeilen 1..16) */
#define MAXLINES 4000
#define MAXIN 120
#define NMODES 7

#ifndef APP_VERSION
#define APP_VERSION "dev"
#endif

typedef struct { Uint8 r, g, b; } Color;
static const Color C_BG = {12, 12, 12};
static const Color C_FG = {235, 235, 235};
static const Color C_OR = {255, 130, 0};
static const Color C_BLACK = {0, 0, 0};
static const Color C_DIM = {135, 135, 135};
static const Color C_GREEN = {80, 220, 100};
static const Color C_AMBER = {255, 200, 60};
static const Color C_BAR = {30, 30, 30};
static const Color C_BOX = {38, 38, 38};

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
};

enum { S_MENU, S_INPUT, S_RUN, S_HELP };
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

static void bar(int row, Color c) { rect(0, row * CH, W, CH, c); }

static void put_char(int x, int y, char c, Color col) {
    if (c >= 'a' && c <= 'z') c = (char)(c - 32);
    if (c < 32 || c > 126) c = '?';
    int idx = c - 32;
    SDL_Rect s = {(idx % 16) * CW, (idx / 16) * CH, CW, CH};
    SDL_Rect d = {x, y, CW, CH};
    SDL_SetTextureColorMod(atlas, col.r, col.g, col.b);
    SDL_RenderCopy(ren, atlas, &s, &d);
}

static void text(int col, int row, const char *s, Color c) {
    for (int i = 0; s[i] && col + i < COLS; i++) put_char((col + i) * CW, row * CH, s[i], c);
}

static void title(const char *left, const char *right) {
    bar(0, C_OR);
    text(1, 0, left, C_BLACK);
    int rl = (int)strlen(right);
    text(COLS - 1 - rl, 0, right, C_BLACK);
}

static void footer(const char *s) {
    bar(ROWS - 1, C_BAR);
    text(1, ROWS - 1, s, C_DIM);
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
    if (idx == NMODES - 1) {
        screen = S_HELP;
    } else {
        mode_idx = idx;
        screen = S_INPUT;
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

static void on_key(const SDL_KeyboardEvent *k, char *kbuf) {
    SDL_Keycode s = k->keysym.sym;
    Uint16 mod = k->keysym.mod;
    int enter = (s == SDLK_RETURN || s == SDLK_KP_ENTER);
    switch (screen) {
    case S_MENU:
        if (s == SDLK_UP) sel = (sel + NMODES - 1) % NMODES;
        else if (s == SDLK_DOWN) sel = (sel + 1) % NMODES;
        else if (enter) activate(sel);
        else if (s >= SDLK_1 && s <= SDLK_7) { sel = (int)(s - SDLK_1); activate(sel); }
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
    }
}

static void on_click(int px, int py) {
    int ww = W, wh = H;
    SDL_GetWindowSize(win, &ww, &wh);
    if (ww <= 0 || wh <= 0) return;
    int x = px * W / ww, y = py * H / wh;
    int col = x / CW, row = y / CH;
    switch (screen) {
    case S_MENU:
        if (row >= 2 && row < 2 + NMODES) { sel = row - 2; activate(sel); }
        break;
    case S_INPUT:
        if (row == 12 && col >= 1 && col <= 11) start_run();
        else if (row == 12 && col >= 14 && col <= 26) screen = S_MENU;
        else if (row == ROWS - 1) screen = S_MENU;
        break;
    case S_RUN:
        if (row == ROWS - 1) go_back_from_run();
        break;
    case S_HELP:
        screen = S_MENU;
        break;
    }
}

static void on_wheel(int dy) {
    if (screen == S_RUN) scroll_by(-dy * 3);
    else if (screen == S_MENU) sel = (sel - dy + NMODES * 8) % NMODES;
}

/* ---------- Bildschirme ---------- */
static void draw_menu(void) {
    title("FLIPPERONE OSINT", "V" APP_VERSION);
    for (int i = 0; i < NMODES; i++) {
        char b[COLS + 1];
        snprintf(b, sizeof b, " %d  %s", i + 1, modes[i].label);
        if (i == sel) {
            bar(2 + i, C_OR);
            text(0, 2 + i, b, C_BLACK);
        } else {
            text(0, 2 + i, b, C_FG);
        }
    }
    rect(CW, 10 * CH + 3, W - 2 * CW, 1, C_DIM);
    text(1, 11, modes[sel].d1, C_DIM);
    text(1, 12, modes[sel].d2, C_DIM);
    footer("HOCH/RUNTER ENTER=OK 1-7=WAHL ESC=ENDE");
}

static void draw_input(void) {
    const Mode *m = &modes[mode_idx];
    char t[COLS + 1];
    snprintf(t, sizeof t, "OSINT > %s", m->label);
    title(t, "");
    char lab[COLS + 1];
    snprintf(lab, sizeof lab, "%s:", m->prompt);
    text(1, 3, lab, C_OR);
    rect(CW - 2, 5 * CH - 3, W - 2 * CW + 4, CH + 6, C_BOX);
    const char *in = inputs[mode_idx];
    int l = (int)strlen(in);
    int vis = COLS - 4;
    const char *shown = l > vis ? in + (l - vis) : in;
    text(2, 5, shown, C_FG);
    int cx = 2 + (int)strlen(shown);
    if ((SDL_GetTicks() / 500) % 2 == 0 && cx < COLS) put_char(cx * CW, 5 * CH, '_', C_OR);
    text(1, 7, m->example, C_DIM);
    text(1, 9, "NUR FUER EIGENE DATEN ODER MIT", C_DIM);
    text(1, 10, "EINWILLIGUNG DER BETROFFENEN NUTZEN.", C_DIM);
    bar(12, C_BG);
    rect(CW, 12 * CH - 1, 11 * CW, CH + 2, C_OR);
    text(2, 12, "START", C_BLACK);
    rect(14 * CW, 12 * CH - 1, 13 * CW, CH + 2, C_BAR);
    text(15, 12, "ZURUECK", C_FG);
    footer("ENTER=START ESC=ZURUECK STRG+V=EINFUEGEN");
}

static void draw_run(void) {
    const Mode *m = &modes[mode_idx];
    char t[COLS + 1];
    snprintf(t, sizeof t, "OSINT > %s", m->label);
    static const char spin[] = "|/-\\";
    char right[16];
    if (running) snprintf(right, sizeof right, "%c LAEUFT", spin[(SDL_GetTicks() / 120) % 4]);
    else snprintf(right, sizeof right, "FERTIG");
    title(t, right);
    static const Color kc[5] = {{235, 235, 235}, {80, 220, 100}, {135, 135, 135}, {255, 200, 60}, {255, 130, 0}};
    for (int r = 0; r < VH; r++) {
        int i = scroll_pos + r;
        if (i >= nlines) break;
        text(0, 1 + r, lines[i].t, kc[lines[i].kind % 5]);
    }
    if (nlines > VH) {
        int track = VH * CH;
        int th = track * VH / nlines;
        if (th < 6) th = 6;
        int max = nlines - VH;
        int ty = CH + (track - th) * scroll_pos / (max > 0 ? max : 1);
        rect(W - 3, CH, 2, track, C_BAR);
        rect(W - 3, ty, 2, th, C_OR);
    }
    footer(running ? "HOCH/RUNTER=SCROLL  ESC=ABBRECHEN"
                   : "SCROLL=HOCH/RUNTER ENTER=NEU ESC=ZURUECK");
}

static void draw_help(void) {
    title("HILFE / INFO", "V" APP_VERSION);
    static const char *h[] = {
        "ALLROUNDER FUER OEFFENTLICHE INFOS:",
        "USERNAME, E-MAIL, TELEFON, DOMAIN, IP.",
        "",
        "BEDIENUNG: HOCH/RUNTER, ENTER, ESC.",
        "TEXT TIPPEN, STRG+V FUEGT EIN.",
        "MAUS: KLICK AUF EINTRAEGE, RAD = SCROLL.",
        "",
        "WICHTIG: NUR FUER EIGENE DATEN ODER",
        "MIT EINWILLIGUNG DER BETROFFENEN.",
        "KEINE PERSONENSUCHE, KEINE HALTERABFRAGE.",
    };
    for (size_t i = 0; i < sizeof h / sizeof h[0]; i++)
        text(1, 2 + (int)i, h[i], i >= 7 ? C_AMBER : C_FG);
    footer("ENTER ODER ESC = ZURUECK");
}

static void render(void) {
    SDL_SetRenderDrawColor(ren, C_BG.r, C_BG.g, C_BG.b, 255);
    SDL_RenderClear(ren);
    switch (screen) {
    case S_MENU: draw_menu(); break;
    case S_INPUT: draw_input(); break;
    case S_RUN: draw_run(); break;
    case S_HELP: draw_help(); break;
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
    SDL_StartTextInput();

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
                if (e.button.button == SDL_BUTTON_LEFT) on_click(e.button.x, e.button.y);
                break;
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
