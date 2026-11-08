/* osint-ui: user interface of FlipperOne-OSINT (SDL2, 256x144 like the TestApp).
 * Usage: osint-ui <path-to-osint-cli>
 * Input: touch/mouse, on-screen keyboard, the Flipper One buttons below the
 * screen (they arrive as the keys Z X C V B), arrow keys, Enter, Esc.
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
static const Color C_BG = {255, 130, 0};     /* background (Flipper One orange, #FF8200) */
static const Color C_INK = {34, 17, 0};      /* text / outlines */
static const Color C_PANEL = {255, 150, 24}; /* menu rows / keys */
static const Color C_DARK = {204, 104, 0};   /* input field / section bars */
static const Color C_SOFT = {125, 60, 0};    /* secondary text */
static const Color C_LIGHT = {255, 176, 80}; /* text on black */

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
    {"USERNAME", "username", "USERNAME", "e.g. maxmuster",
     "Checks whether the name is taken on", "30+ public platforms."},
    {"EMAIL ADDRESS", "email", "EMAIL ADDRESS", "e.g. name@example.com",
     "Syntax, mail server, SPF/DMARC,", "Gravatar, provider, domain data."},
    {"PHONE NUMBER", "phone", "PHONE NUMBER", "e.g. +49 171 1234567",
     "Country, format and line type", "(offline). No owner lookup."},
    {"DOMAIN / WEBSITE", "domain", "DOMAIN", "e.g. example.com",
     "DNS, registrar, web server, TLS,", "headers and subdomains (cert logs)."},
    {"IP ADDRESS", "ip", "IP ADDRESS", "e.g. 8.8.8.8",
     "rDNS, operator, country, open ports", "and known vulnerabilities."},
    {"NAME -> USERNAMES", "name", "FIRST AND LAST NAME", "e.g. Max Mustermann",
     "Generates username variants from a", "name (text only, no search)."},
    {"HELP / INFO", NULL, NULL, NULL, "Controls and notes.", ""},
    {"KEY TEST", NULL, NULL, NULL, "Shows the codes of the Flipper buttons", "and of touch input."},
};

enum { S_MENU, S_INPUT, S_RUN, S_HELP, S_KEYS };
static int screen = S_MENU;
static int sel = 0;
static int mode_idx = 0;
static char inputs[NMODES][MAXIN + 1];
static int cur[NMODES];   /* text cursor position per mode */
static int view_off = 0;  /* first visible character of the input field */
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
static char btn_char = 0;          /* last Flipper button seen as a letter key (to drop its text event) */
static int kb_r = 1, kb_c = 0;    /* focused on-screen key (arrow-key navigation) */
static int shift_on = 0;           /* on-screen keyboard: next letter is upper case */
static int flash_row = -1, flash_col = -1;
static Uint32 flash_until = 0;

/* ---------- on-screen keyboard ---------- */
enum { K_CHAR, K_BKSP, K_SHIFT, K_SPACE };
typedef struct { int x, w; char ch; int kind; } Key;
#define OSK_ROWS 5
#define OSK_Y0 36
#define OSK_RH 18
#define OSK_CELL 25
static Key osk[OSK_ROWS][10];
static int osk_n[OSK_ROWS];

static void osk_add(int r, int cell, int span, char ch, int kind) {
    Key *k = &osk[r][osk_n[r]++];
    k->x = 3 + cell * OSK_CELL;
    k->w = span * OSK_CELL - 2;
    k->ch = ch;
    k->kind = kind;
}

static void osk_init(void) {
    const char *r0 = "1234567890", *r1 = "qwertyuiop", *r2 = "asdfghjkl", *r3 = "zxcvbnm.-";
    for (int i = 0; i < 10; i++) osk_add(0, i, 1, r0[i], K_CHAR);
    for (int i = 0; i < 10; i++) osk_add(1, i, 1, r1[i], K_CHAR);
    for (int i = 0; i < 9; i++) osk_add(2, i, 1, r2[i], K_CHAR);
    osk_add(2, 9, 1, 0, K_BKSP);
    osk_add(3, 0, 1, 0, K_SHIFT);
    for (int i = 0; i < 9; i++) osk_add(3, 1 + i, 1, r3[i], K_CHAR);
    const char *r4 = "@_+:/";
    for (int i = 0; i < 5; i++) osk_add(4, i, 1, r4[i], K_CHAR);
    osk_add(4, 5, 4, ' ', K_SPACE);
    osk_add(4, 9, 1, ',', K_CHAR);
}

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

/* Rounded box: outline + fill, corner pixels cut. */
static void rbox(int x, int y, int w, int h, Color line, Color fill) {
    rect(x, y, w, h, line);
    rect(x + 1, y + 1, w - 2, h - 2, fill);
    rect(x, y, 1, 1, C_BG);
    rect(x + w - 1, y, 1, 1, C_BG);
    rect(x, y + h - 1, 1, 1, C_BG);
    rect(x + w - 1, y + h - 1, 1, 1, C_BG);
}

/* The 5 Flipper buttons below the screen = 5 tab slots: Z X C V B.
 * Slot 2 (C) is the power button and carries no label. */
#define SLOTW 51
static void tab(int slot, const char *s, int primary) {
    if (!s || !*s) return;
    int x = 1 + slot * SLOTW, w = SLOTW - 2, y = H - TABH;
    rect(x, y, w, TABH, C_INK);
    rect(x + 1, y + 1, w - 2, TABH - 1, primary ? C_INK : C_PANEL);
    rect(x, y, 1, 1, C_BG);
    rect(x + w - 1, y, 1, 1, C_BG);
    int tw = (int)strlen(s) * CW;
    text_px(x + (w - tw) / 2, y + 3, s, primary ? C_LIGHT : C_INK);
}

static void softkeys(const char *z, const char *x, const char *v, const char *b) {
    tab(0, z, 0);
    tab(1, x, 0);
    tab(3, v, 0);
    tab(4, b, 1);
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
                push_result("! Backend (osint-cli) not found");
            else
                push_result("! No output from backend");
        } else if (WIFEXITED(status) && WEXITSTATUS(status) != 0) {
            char b[64];
            snprintf(b, sizeof b, "! Backend exited with code %d", WEXITSTATUS(status));
            push_result(b);
        }
        return;
    }
}

static void start_run(void) {
    char *in = inputs[mode_idx];
    size_t l = strlen(in);
    while (l > 0 && in[l - 1] == ' ') in[--l] = 0;
    if (cur[mode_idx] > (int)l) cur[mode_idx] = (int)l;
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
        push_result("! Could not start backend");
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

/* ---------- text field editing (insert / delete at the cursor) ---------- */
static void in_insert(char c) {
    char *in = inputs[mode_idx];
    int l = (int)strlen(in), p = cur[mode_idx];
    if (l >= MAXIN) return;
    if (p > l) p = l;
    if (p < 0) p = 0;
    memmove(in + p + 1, in + p, (size_t)(l - p + 1));
    in[p] = c;
    cur[mode_idx] = p + 1;
}

static void in_delete(void) { /* delete the character before the cursor */
    char *in = inputs[mode_idx];
    int l = (int)strlen(in), p = cur[mode_idx];
    if (p > l) p = l;
    if (p <= 0) return;
    memmove(in + p - 1, in + p, (size_t)(l - p + 1));
    cur[mode_idx] = p - 1;
}

static void in_clear(void) {
    inputs[mode_idx][0] = 0;
    cur[mode_idx] = 0;
    view_off = 0;
}

static void in_move(int d) {
    int l = (int)strlen(inputs[mode_idx]);
    int p = cur[mode_idx] + d;
    cur[mode_idx] = p < 0 ? 0 : (p > l ? l : p);
}

static void append_input(const char *s) {
    for (; *s; s++)
        if ((unsigned char)*s >= 32 && (unsigned char)*s <= 126) in_insert(*s);
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
static void osk_move(int dr, int dc);
static void osk_enter(void);
static void act_back(void);
static void act_x(void);

static void on_key(const SDL_KeyboardEvent *k, char *kbuf) {
    SDL_Keycode s = k->keysym.sym;
    Uint16 mod = k->keysym.mod;
    int enter = (s == SDLK_RETURN || s == SDLK_KP_ENTER);
    log_event("KEY %s SYM=%X SC=%d", (int)s, (int)k->keysym.scancode, SDL_GetKeyName(s));
    if (screen == S_KEYS) {
        if (s == SDLK_ESCAPE || s == SDLK_BACKSPACE || s == SDLK_AC_BACK || s == SDLK_CANCEL || s == 'z') {
            if (++esc_streak >= 3) screen = S_MENU;
        } else {
            esc_streak = 0;
        }
        return;
    }
    /* The five Flipper buttons arrive as the keys Z X C V B (left to right). */
    if (!(mod & (KMOD_CTRL | KMOD_ALT | KMOD_GUI | KMOD_SHIFT))) {
        if (s == 'z') { btn_char = 'z'; softkey(0); return; }
        if (s == 'x') { btn_char = 'x'; softkey(1); return; }
        if (s == 'c') { btn_char = 'c'; return; }
        if (s == 'v') { btn_char = 'v'; softkey(3); return; }
        if (s == 'b') { btn_char = 'b'; softkey(4); return; }
    }
    /* other back/menu/ok key codes */
    if (s == SDLK_AC_BACK || s == SDLK_CANCEL || s == SDLK_BACKSPACE) { act_back(); return; }
    if (s == SDLK_MENU || s == SDLK_APPLICATION) { act_x(); return; }
    if (s == SDLK_SELECT || s == SDLK_EXECUTE) { softkey(4); return; }
    if (s == SDLK_F1) { softkey(0); return; }
    if (s == SDLK_F2) { softkey(1); return; }
    if (s == SDLK_F3) { softkey(4); return; }
    if (s == SDLK_F4) { softkey(3); return; }
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
        else if (s == SDLK_UP) osk_move(-1, 0);
        else if (s == SDLK_DOWN) osk_move(1, 0);
        else if (s == SDLK_LEFT) osk_move(0, -1);
        else if (s == SDLK_RIGHT) osk_move(0, 1);
        else if (enter) osk_enter();
        else if (s == 'v' && (mod & KMOD_CTRL)) {
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

static Key *osk_hit(int x, int y, int *row) {
    int r = (y - OSK_Y0) / OSK_RH;
    if (y < OSK_Y0 || r < 0 || r >= OSK_ROWS || (y - OSK_Y0) % OSK_RH >= 16) return NULL;
    for (int i = 0; i < osk_n[r]; i++)
        if (x >= osk[r][i].x && x < osk[r][i].x + osk[r][i].w) {
            *row = r;
            kb_r = r;
            kb_c = i;
            flash_row = r;
            flash_col = i;
            flash_until = SDL_GetTicks() + 120;
            return &osk[r][i];
        }
    return NULL;
}

static void osk_press(const Key *k) {
    switch (k->kind) {
    case K_BKSP: in_delete(); break;
    case K_SHIFT: shift_on = !shift_on; break;
    default: {
        char c = k->ch;
        if (shift_on && c >= 'a' && c <= 'z') c = (char)(c - 32);
        in_insert(c);
        shift_on = 0;
    }
    }
}

static void osk_move(int dr, int dc) {
    if (dc) {
        kb_c = (kb_c + dc + osk_n[kb_r]) % osk_n[kb_r];
        return;
    }
    int cx = osk[kb_r][kb_c].x + osk[kb_r][kb_c].w / 2;
    int r2 = (kb_r + dr + OSK_ROWS) % OSK_ROWS;
    int best = 0, bd = 1 << 30;
    for (int i = 0; i < osk_n[r2]; i++) {
        int d = osk[r2][i].x + osk[r2][i].w / 2 - cx;
        if (d < 0) d = -d;
        if (d < bd) { bd = d; best = i; }
    }
    kb_r = r2;
    kb_c = best;
}

static void osk_enter(void) {
    osk_press(&osk[kb_r][kb_c]);
    flash_row = kb_r;
    flash_col = kb_c;
    flash_until = SDL_GetTicks() + 120;
}

#define MENU_Y0 13
#define MENU_P 10

/* Button semantics (the five buttons below the screen + Backspace key):
 *   Z  = text field: cursor left   | elsewhere: close the app
 *   X  = text field: cursor right  | menu: help, results: jump to top
 *   V  = text field: clear         | elsewhere: one step back
 *   B  = OK: open / start / run again
 *   Backspace = text field: delete before cursor | elsewhere: one step back
 */
static void act_exit(void) { quit = 1; }

/* Backspace key / back: delete in the text field, otherwise one step back. */
static void act_back(void) {
    switch (screen) {
    case S_MENU: quit = 1; break;
    case S_INPUT:
        if (inputs[mode_idx][0] == 0) screen = S_MENU;
        else in_delete();
        break;
    case S_RUN: go_back_from_run(); break;
    default: screen = S_MENU; break;
    }
}

/* Z button */
static void act_z(void) {
    if (screen == S_INPUT) in_move(-1);
    else act_exit();
}

/* X button */
static void act_x(void) {
    switch (screen) {
    case S_MENU: screen = S_HELP; break;
    case S_INPUT: in_move(1); break;
    case S_RUN: scroll_by(-MAXLINES); break;
    default: screen = S_MENU; break;
    }
}

/* V button */
static void act_v(void) {
    if (screen == S_INPUT) in_clear();
    else act_back();
}

static void act_ok(void) {
    switch (screen) {
    case S_MENU: activate(sel); break;
    case S_INPUT: start_run(); break;
    case S_RUN: if (finished) start_run(); break;
    case S_HELP: screen = S_MENU; break;
    default: break;
    }
}

/* n = button slot: 0 = Z, 1 = X, 3 = V, 4 = B */
static void softkey(int n) {
    if (n == 0) act_z();
    else if (n == 1) act_x();
    else if (n == 3) act_v();
    else if (n == 4) act_ok();
}

static void on_click(int px, int py) {
    int ww = W, wh = H;
    SDL_GetWindowSize(win, &ww, &wh);
    if (ww <= 0 || wh <= 0) return;
    int x = px * W / ww, y = py * H / wh;
    log_event("%s X=%d Y=%d", x, y, "TOUCH");
    if (screen == S_KEYS) {
        if (y >= H - TABH && x < 86) screen = S_MENU;
        return;
    }
    if (y >= H - TABH) {
        softkey(x / SLOTW);
        return;
    }
    if (screen == S_INPUT) {
        int row = 0;
        Key *k = osk_hit(x, y, &row);
        if (k) osk_press(k);
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
        rbox(4, y - 1, W - 8, 10, C_INK, i == sel ? C_INK : C_PANEL);
        text_px(10, y, b, i == sel ? C_LIGHT : C_INK);
    }
    text_px(4, 99, modes[sel].d1, C_SOFT);
    text_px(4, 108, modes[sel].d2, C_SOFT);
    softkeys("EXIT", "HELP", NULL, "OPEN");
}

static void draw_osk(void) {
    for (int r = 0; r < OSK_ROWS; r++) {
        int y = OSK_Y0 + r * OSK_RH;
        for (int i = 0; i < osk_n[r]; i++) {
            const Key *k = &osk[r][i];
            int flash = (r == flash_row && i == flash_col && SDL_GetTicks() < flash_until);
            int focus = (r == kb_r && i == kb_c);
            int dark = flash || focus;
            rbox(k->x, y, k->w, 16, C_INK, dark ? C_INK : C_PANEL);
            const char *lab;
            char one[2] = {k->ch, 0};
            switch (k->kind) {
            case K_BKSP: lab = "<"; break;
            case K_SHIFT: lab = "^"; break;
            case K_SPACE: lab = "SPACE"; break;
            default: lab = one;
            }
            int tw = (int)strlen(lab) * CW;
            text_px(k->x + (k->w - tw) / 2, y + 4, lab, dark ? C_LIGHT : C_INK);
            if (k->kind == K_SHIFT && shift_on) { /* active shift: inner frame */
                rect(k->x + 3, y + 3, k->w - 6, 1, dark ? C_LIGHT : C_INK);
                rect(k->x + 3, y + 12, k->w - 6, 1, dark ? C_LIGHT : C_INK);
            }
        }
    }
}

static void draw_input(void) {
    const Mode *m = &modes[mode_idx];
    title("OSINT", m->prompt);
    rbox(4, 10, W - 8, 14, C_INK, C_DARK);
    const char *in = inputs[mode_idx];
    int l = (int)strlen(in);
    int vis = (W - 24) / CW;
    int c = cur[mode_idx] > l ? l : cur[mode_idx];
    if (c < view_off) view_off = c;
    if (c > view_off + vis - 1) view_off = c - (vis - 1);
    if (view_off < 0) view_off = 0;
    if (l == 0) text_px(10, 14, m->example, C_SOFT);
    else text_px(10, 14, in + view_off, C_INK);
    if ((SDL_GetTicks() / 500) % 2 == 0) rect(10 + (c - view_off) * CW - 1, 12, 1, 10, C_INK);
    draw_osk();
    softkeys("<", ">", "CLEAR", "START");
}

static void draw_run(void) {
    static const char spin[] = "|/-\\";
    char right[24];
    if (running) snprintf(right, sizeof right, "%c RUNNING", spin[(SDL_GetTicks() / 120) % 4]);
    else snprintf(right, sizeof right, "DONE");
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
    if (running) softkeys("EXIT", "TOP", "STOP", NULL);
    else softkeys("EXIT", "TOP", "BACK", "AGAIN");
}

static void draw_help(void) {
    title("HELP / INFO", "V" APP_VERSION);
    static const char *h[] = {
        "All-in-one tool for public information:",
        "username, email, phone, domain, IP.",
        "",
        "Z / X move the cursor in the text field,",
        "V clears it, Backspace deletes, B = OK.",
        "Arrows move the keyboard focus, Enter",
        "presses a key. Touch / mouse works too.",
        "",
        "No people search, no owner lookup.",
    };
    static const Color red = {150, 18, 0};
    for (size_t i = 0; i < sizeof h / sizeof h[0]; i++)
        text_px(4, 14 + (int)i * 10, h[i], i >= 9 ? red : C_INK);
    softkeys("EXIT", NULL, "BACK", NULL);
}

static void draw_keys(void) {
    title("KEY TEST", "");
    text_px(4, 12, "Press buttons / tap the screen:", C_INK);
    for (int i = 0; i < keylog_n; i++) text_px(4, 24 + i * 10, keylog[i], i == 0 ? C_INK : C_SOFT);
    text_px(4, 116, "Backspace 3x = back", C_SOFT);
    softkeys("EXIT", NULL, "BACK", NULL);
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
    osk_init();

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
                if (btn_char && e.text.text[0] == btn_char && e.text.text[1] == 0) { btn_char = 0; break; }
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
        btn_char = 0;
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
