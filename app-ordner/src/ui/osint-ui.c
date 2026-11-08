/* osint-ui: user interface of FlipperOne-OSINT (SDL2, 256x144 like the TestApp).
 * Usage: osint-ui <path-to-osint-cli>
 * Input: the Flipper One buttons below the screen (they arrive as the keys
 * Z X C V B), the Backspace key, arrow keys + Enter, touch/mouse.
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
#define CH 9
#define COLS (W / CW) /* 42 characters per line */
#define HDR 14        /* header height */
#define VH 12         /* visible result rows */
#define TABH 14       /* height of the button tab bar at the bottom */
#define MAXLINES 4000
#define MAXIN 120
#define NMODES 5

#ifndef APP_VERSION
#define APP_VERSION "dev"
#endif

typedef struct { Uint8 r, g, b; } Color;
/* Flipper One look: orange (#FF8200) with dark ink */
static const Color C_BG = {255, 130, 0};
static const Color C_INK = {34, 17, 0};
static const Color C_PILL = {232, 112, 0};   /* flat buttons / rows */
static const Color C_FIELD = {204, 104, 0};  /* text field */
static const Color C_SOFT = {128, 62, 0};    /* secondary text */
static const Color C_LIGHT = {255, 176, 80}; /* text on dark */
static const Color C_GREEN = {10, 110, 30};
static const Color C_RED = {160, 20, 0};

/* ---------- 5x8 font (upper and lower case) ---------- */
typedef struct { char c; const char *r[8]; } Glyph;
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
    {'a', {".....", ".....", ".XXX.", "....X", ".XXXX", "X...X", ".XXXX", "....."}},
    {'b', {"X....", "X....", "XXXX.", "X...X", "X...X", "X...X", "XXXX.", "....."}},
    {'c', {".....", ".....", ".XXX.", "X...X", "X....", "X...X", ".XXX.", "....."}},
    {'d', {"....X", "....X", ".XXXX", "X...X", "X...X", "X...X", ".XXXX", "....."}},
    {'e', {".....", ".....", ".XXX.", "X...X", "XXXXX", "X....", ".XXX.", "....."}},
    {'f', {"..XX.", ".X..X", ".X...", "XXX..", ".X...", ".X...", ".X...", "....."}},
    {'g', {".....", ".....", ".XXXX", "X...X", "X...X", ".XXXX", "....X", ".XXX."}},
    {'h', {"X....", "X....", "XXXX.", "X...X", "X...X", "X...X", "X...X", "....."}},
    {'i', {"..X..", ".....", ".XX..", "..X..", "..X..", "..X..", ".XXX.", "....."}},
    {'j', {"...X.", ".....", "..XX.", "...X.", "...X.", "...X.", "X..X.", ".XX.."}},
    {'k', {"X....", "X....", "X..X.", "X.X..", "XX...", "X.X..", "X..X.", "....."}},
    {'l', {".XX..", "..X..", "..X..", "..X..", "..X..", "..X..", ".XXX.", "....."}},
    {'m', {".....", ".....", "XX.X.", "X.X.X", "X.X.X", "X.X.X", "X.X.X", "....."}},
    {'n', {".....", ".....", "XXXX.", "X...X", "X...X", "X...X", "X...X", "....."}},
    {'o', {".....", ".....", ".XXX.", "X...X", "X...X", "X...X", ".XXX.", "....."}},
    {'p', {".....", ".....", "XXXX.", "X...X", "X...X", "XXXX.", "X....", "X...."}},
    {'q', {".....", ".....", ".XXXX", "X...X", "X...X", ".XXXX", "....X", "....X"}},
    {'r', {".....", ".....", "X.XX.", "XX..X", "X....", "X....", "X....", "....."}},
    {'s', {".....", ".....", ".XXXX", "X....", ".XXX.", "....X", "XXXX.", "....."}},
    {'t', {".....", ".X...", "XXXX.", ".X...", ".X...", ".X..X", "..XX.", "....."}},
    {'u', {".....", ".....", "X...X", "X...X", "X...X", "X..XX", ".XX.X", "....."}},
    {'v', {".....", ".....", "X...X", "X...X", "X...X", ".X.X.", "..X..", "....."}},
    {'w', {".....", ".....", "X...X", "X.X.X", "X.X.X", "X.X.X", ".X.X.", "....."}},
    {'x', {".....", ".....", "X...X", ".X.X.", "..X..", ".X.X.", "X...X", "....."}},
    {'y', {".....", ".....", "X...X", "X...X", "X...X", ".XXXX", "....X", ".XXX."}},
    {'z', {".....", ".....", "XXXXX", "...X.", "..X..", ".X...", "XXXXX", "....."}},
};

/* ---------- state ---------- */
typedef struct {
    const char *label, *cmd, *prompt, *example, *d1, *d2;
} Mode;

static const Mode modes[NMODES] = {
    {"Username", "username", "Username", "e.g. maxmuster",
     "Checks whether the name is taken on", "30+ public platforms."},
    {"Email address", "email", "Email address", "e.g. name@example.com",
     "Syntax, mail server, SPF/DMARC,", "Gravatar, provider, domain data."},
    {"Phone number", "phone", "Phone number", "e.g. +49 171 1234567",
     "Country, format and line type", "(offline). No owner lookup."},
    {"Domain / website", "domain", "Domain", "e.g. example.com",
     "DNS, registrar, web server, TLS,", "headers and subdomains."},
    {"IP address", "ip", "IP address", "e.g. 8.8.8.8",
     "rDNS, operator, country, open ports", "and known vulnerabilities."},
};

enum { S_MENU, S_INPUT, S_RUN };
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

static int drag_active = 0, drag_last_y = 0, drag_acc = 0;
static char btn_char = 0;          /* last Flipper button seen as a letter key (to drop its text event) */
static int kb_r = 1, kb_c = 0;    /* focused on-screen key */
static int shift_on = 0;           /* on-screen keyboard: upper case (toggle) */
static int flash_row = -1, flash_col = -1;
static Uint32 flash_until = 0;

static SDL_Window *win;
static SDL_Renderer *ren;
static SDL_Texture *atlas;

static void log_key(const char *what, int a, int b) {
    fprintf(stderr, "%s %d %d\n", what, a, b);
}

/* ---------- drawing primitives ---------- */
#define ATLAS_W 96
#define ATLAS_H (6 * CH)

static void build_atlas(void) {
    static Uint32 px[ATLAS_W * ATLAS_H];
    memset(px, 0, sizeof px);
    for (size_t g = 0; g < sizeof glyphs / sizeof glyphs[0]; g++) {
        int idx = glyphs[g].c - 32;
        int gx = (idx % 16) * CW, gy = (idx / 16) * CH;
        for (int y = 0; y < 8; y++) {
            if (!glyphs[g].r[y]) continue;
            for (int x = 0; x < 5; x++)
                if (glyphs[g].r[y][x] == 'X') px[(gy + y) * ATLAS_W + gx + x] = 0xFFFFFFFFu;
        }
    }
    atlas = SDL_CreateTexture(ren, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STATIC, ATLAS_W, ATLAS_H);
    if (atlas) {
        SDL_UpdateTexture(atlas, NULL, px, ATLAS_W * 4);
        SDL_SetTextureBlendMode(atlas, SDL_BLENDMODE_BLEND);
    }
}

static void rect(int x, int y, int w, int h, Color c) {
    SDL_SetRenderDrawColor(ren, c.r, c.g, c.b, 255);
    SDL_Rect rc = {x, y, w, h};
    SDL_RenderFillRect(ren, &rc);
}

/* flat rounded box (radius 2) */
static void pill(int x, int y, int w, int h, Color c) {
    rect(x + 2, y, w - 4, h, c);
    rect(x + 1, y + 1, w - 2, h - 2, c);
    rect(x, y + 2, w, h - 4, c);
}

static void put_char(int x, int y, char c, Color col) {
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

static void text_bold(int x, int y, const char *s, Color c) {
    text_px(x, y, s, c);
    text_px(x + 1, y, s, c);
}

static void icon(int x, int y) { /* small magnifier */
    rect(x, y, 5, 1, C_INK);
    rect(x, y + 4, 5, 1, C_INK);
    rect(x, y, 1, 5, C_INK);
    rect(x + 4, y, 1, 5, C_INK);
    rect(x + 5, y + 5, 2, 2, C_INK);
}

static void title(const char *right) {
    icon(6, 3);
    text_bold(17, 3, "OSINT", C_INK);
    int rl = (int)strlen(right);
    text_px(W - 6 - rl * CW, 3, right, C_SOFT);
}

/* The 5 Flipper buttons below the screen = 5 tab slots (Z X C V B).
 * Slot 2 (C) is the power button and carries no label. */
#define SLOTW 51
static void tab(int slot, const char *s, int primary) {
    if (!s || !*s) return;
    int x = 2 + slot * SLOTW, w = SLOTW - 4, y = H - TABH;
    pill(x, y, w, TABH + 6, primary ? C_INK : C_PILL); /* bottom part is clipped */
    int tw = (int)strlen(s) * CW;
    text_px(x + (w - tw) / 2, y + 3, s, primary ? C_LIGHT : C_INK);
}

static void softkeys(const char *z, const char *x, const char *v, const char *b) {
    tab(0, z, 0);
    tab(1, x, 0);
    tab(3, v, 0);
    tab(4, b, 1);
}

/* ---------- result lines ---------- */
static void add_line(const char *s, int kind) {
    if (nlines >= MAXLINES) return;
    strncpy(lines[nlines].t, s, COLS);
    lines[nlines].t[COLS] = 0;
    lines[nlines].kind = (unsigned char)kind;
    nlines++;
    if (follow) scroll_pos = nlines > VH ? nlines - VH : 0;
}

static void wrap_add(char m, const char *s, int kind) {
    const int width = COLS - 3;
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

/* ---------- backend process ---------- */
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
        /* EOF or error */
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

static void activate(int idx) {
    mode_idx = idx;
    screen = S_INPUT;
    SDL_StartTextInput();
}

/* ---------- on-screen keyboard ---------- */
enum { K_CHAR, K_BKSP, K_SHIFT, K_SPACE };
typedef struct { int x, w; char ch; int kind; } Key;
#define OSK_ROWS 5
#define OSK_Y0 38
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

static Key *osk_hit(int x, int y) {
    int r = (y - OSK_Y0) / OSK_RH;
    if (y < OSK_Y0 || r < 0 || r >= OSK_ROWS || (y - OSK_Y0) % OSK_RH >= 16) return NULL;
    for (int i = 0; i < osk_n[r]; i++)
        if (x >= osk[r][i].x && x < osk[r][i].x + osk[r][i].w) {
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

/* ---------- button actions ----------
 *   Z  = text field: cursor left   | results/menu: close the app
 *   X  = text field: cursor right  | results: jump to top
 *   V  = text field: clear         | results: stop / refresh
 *   B  = OK: open / start / search again
 *   Backspace = text field: delete before cursor | otherwise one step back (never closes the app)
 */
static void act_back(void) {
    switch (screen) {
    case S_INPUT:
        if (inputs[mode_idx][0] == 0) screen = S_MENU;
        else in_delete();
        break;
    case S_RUN: go_back_from_run(); break;
    default: break;
    }
}

static void act_z(void) {
    if (screen == S_INPUT) in_move(-1);
    else quit = 1;
}

static void act_x(void) {
    if (screen == S_INPUT) in_move(1);
    else if (screen == S_RUN) scroll_by(-MAXLINES);
}

static void act_v(void) {
    if (screen == S_INPUT) {
        in_clear();
    } else if (screen == S_RUN) {
        if (running) {
            stop_child();
            finished = 1;
            push_result("i Stopped");
        } else {
            start_run();
        }
    }
}

static void act_ok(void) {
    switch (screen) {
    case S_MENU: activate(sel); break;
    case S_INPUT: start_run(); break;
    case S_RUN: go_back_from_run(); break;
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

static void on_key(const SDL_KeyboardEvent *k, char *kbuf) {
    SDL_Keycode s = k->keysym.sym;
    Uint16 mod = k->keysym.mod;
    int enter = (s == SDLK_RETURN || s == SDLK_KP_ENTER);
    log_key("key", (int)s, (int)k->keysym.scancode);
    /* The five Flipper buttons arrive as the keys Z X C V B (left to right). */
    if (!(mod & (KMOD_CTRL | KMOD_ALT | KMOD_GUI | KMOD_SHIFT))) {
        if (s == 'z') { btn_char = 'z'; softkey(0); return; }
        if (s == 'x') { btn_char = 'x'; softkey(1); return; }
        if (s == 'c') { btn_char = 'c'; return; }
        if (s == 'v') { btn_char = 'v'; softkey(3); return; }
        if (s == 'b') { btn_char = 'b'; softkey(4); return; }
    }
    if (s == SDLK_AC_BACK || s == SDLK_CANCEL || s == SDLK_BACKSPACE) {
        /* A held key (auto-repeat) must never carry on past the field into
         * the menu or out of a screen: repeats only delete characters. */
        if (k->repeat && !(screen == S_INPUT && inputs[mode_idx][0])) return;
        act_back();
        return;
    }
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
        else if (s >= SDLK_1 && s <= SDLK_5) { sel = (int)(s - SDLK_1); activate(sel); }
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
    }
}

#define MENU_Y0 17
#define MENU_P 18
#define MENU_H 15

static void on_click(int px, int py) {
    int ww = W, wh = H;
    SDL_GetWindowSize(win, &ww, &wh);
    if (ww <= 0 || wh <= 0) return;
    int x = px * W / ww, y = py * H / wh;
    if (y >= H - TABH) {
        softkey(x / SLOTW);
        return;
    }
    if (screen == S_INPUT) {
        Key *k = osk_hit(x, y);
        if (k) osk_press(k);
        return;
    }
    if (screen == S_MENU) {
        int i = (y - MENU_Y0 + 2) / MENU_P;
        if (y >= MENU_Y0 - 2 && i >= 0 && i < NMODES) { sel = i; activate(sel); }
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

/* ---------- screens ---------- */
static void draw_menu(void) {
    title("v" APP_VERSION);
    for (int i = 0; i < NMODES; i++) {
        int y = MENU_Y0 + i * MENU_P;
        int on = (i == sel);
        pill(6, y, W - 12, MENU_H, on ? C_INK : C_PILL);
        text_px(14, y + 4, modes[i].label, on ? C_LIGHT : C_INK);
        if (on) text_px(W - 20, y + 4, ">", C_LIGHT);
    }
    text_px(8, 111, modes[sel].d1, C_SOFT);
    text_px(8, 120, modes[sel].d2, C_SOFT);
    softkeys("Exit", NULL, NULL, "Open");
}

static void draw_osk(void) {
    for (int r = 0; r < OSK_ROWS; r++) {
        int y = OSK_Y0 + r * OSK_RH;
        for (int i = 0; i < osk_n[r]; i++) {
            const Key *k = &osk[r][i];
            int focus = (r == kb_r && i == kb_c);
            int flash = (r == flash_row && i == flash_col && SDL_GetTicks() < flash_until);
            int dark = focus || flash || (k->kind == K_SHIFT && shift_on);
            pill(k->x, y, k->w, 16, dark ? C_INK : C_PILL);
            const char *lab;
            char one[2] = {k->ch, 0};
            if (k->kind == K_CHAR && shift_on && k->ch >= 'a' && k->ch <= 'z') one[0] = (char)(k->ch - 32);
            switch (k->kind) {
            case K_BKSP: lab = "<"; break;
            case K_SHIFT: lab = shift_on ? "ABC" : "abc"; break;
            case K_SPACE: lab = "space"; break;
            default: lab = one;
            }
            int tw = (int)strlen(lab) * CW;
            text_px(k->x + (k->w - tw) / 2, y + 4, lab, dark ? C_LIGHT : C_INK);
        }
    }
}

static void draw_input(void) {
    const Mode *m = &modes[mode_idx];
    title(m->prompt);
    pill(6, 17, W - 12, 17, C_FIELD);
    const char *in = inputs[mode_idx];
    int l = (int)strlen(in);
    int vis = (W - 28) / CW;
    int c = cur[mode_idx] > l ? l : cur[mode_idx];
    if (c < view_off) view_off = c;
    if (c > view_off + vis - 1) view_off = c - (vis - 1);
    if (view_off < 0) view_off = 0;
    if (l == 0) text_px(14, 22, m->example, C_SOFT);
    else text_px(14, 22, in + view_off, C_INK);
    if ((SDL_GetTicks() / 500) % 2 == 0) rect(14 + (c - view_off) * CW - 1, 20, 1, 11, C_INK);
    draw_osk();
    softkeys("<", ">", "Clear", "Start");
}

static void draw_run(void) {
    static const char spin[] = "|/-\\";
    char right[24];
    if (running) snprintf(right, sizeof right, "%c Running", spin[(SDL_GetTicks() / 120) % 4]);
    else snprintf(right, sizeof right, "Done");
    title(right);
    for (int r = 0; r < VH; r++) {
        int i = scroll_pos + r;
        if (i >= nlines) break;
        int y = HDR + r * CH + 1;
        const Line *ln = &lines[i];
        char mk = ln->t[0];
        if (ln->kind == 4) {
            pill(4, y - 1, W - 12, CH + 1, C_FIELD);
            text_bold(10, y, ln->t + 2, C_INK);
            continue;
        }
        Color tc = ln->kind == 2 ? C_SOFT : (ln->kind == 3 ? C_RED : C_INK);
        if (mk == '+') rect(5, y + 2, 3, 3, C_GREEN);
        else if (mk == '-') rect(5, y + 2, 3, 3, C_SOFT);
        else if (mk == '!') rect(5, y + 2, 3, 3, C_RED);
        text_px(12, y, ln->t + 2, tc);
    }
    if (nlines > VH) {
        int track = VH * CH;
        int th = track * VH / nlines;
        if (th < 6) th = 6;
        int max = nlines - VH;
        int ty = HDR + (track - th) * scroll_pos / (max > 0 ? max : 1);
        rect(W - 3, HDR, 1, track, C_FIELD);
        rect(W - 4, ty, 3, th, C_INK);
    }
    softkeys("Exit", "Top", running ? "Stop" : "Refresh", "Again");
}

static void render(void) {
    SDL_SetRenderDrawColor(ren, C_BG.r, C_BG.g, C_BG.b, 255);
    SDL_RenderClear(ren);
    switch (screen) {
    case S_MENU: draw_menu(); break;
    case S_INPUT: draw_input(); break;
    case S_RUN: draw_run(); break;
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
