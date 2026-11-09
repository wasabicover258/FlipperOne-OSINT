/* osint-ui: user interface of FlipperOne-OSINT (SDL2, 256x144 like the TestApp).
 * Usage: osint-ui <path-to-osint-cli>
 * Input: the Flipper One buttons below the screen (they arrive as the keys
 * Z X C V B), the Backspace key, arrow keys + Enter, touch/mouse.
 *
 * The menu carries the infrastructure modules (unchanged) and the person modules that run
 * through PersonIntel. It scrolls, so more entries than fit on the panel are reachable with
 * the d-pad alone.
 *
 * An "active check" contacts third parties on behalf of the research. Those modes never start
 * from the input screen: they go through a confirmation screen first, where the identifier is
 * shown again and two statements have to be ticked. Only then does the backend receive the
 * word "confirm" as its third argument - without it PersonIntel refuses the query.
 *
 * Result markers from the backend: + found, - not found, ! warning, i info, # section,
 * and for person findings the evidence level: = proven, ~ indication, ? unconfirmed.
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
/* evidence levels: proven / indication / unconfirmed */
static const Color C_PROVEN = {8, 92, 26};
static const Color C_INDIC = {120, 58, 0};
static const Color C_UNCONF = {128, 62, 0};

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
/* MF_NOINPUT: no text field, runs straight away.
 * MF_ACTIVE:  contacts third parties -> confirmation screen before the run. */
#define MF_NOINPUT 1u
#define MF_ACTIVE 2u

typedef struct {
    const char *label, *cmd, *prompt, *example, *d1, *d2;
    unsigned flags;
} Mode;

static const Mode modes[] = {
    /* One familiar starting point; public checks begin without modal screens.
     * Third-party account registration probes remain explicit opt-in via CLI. */
    {"Phone number", "combo-phone", "Phone number", "e.g. +49 171 1234567",
     "Number format and public details", "from available sources.", 0},
    {"Email address", "combo-email", "Email address", "e.g. name@example.com",
     "Mail provider, DNS and security", "in one result view.", 0},
    {"Username", "combo-username", "Username", "e.g. examplehandle",
     "Checks public account pages", "across available platforms.", 0},
    {"Full name", "person-name", "Full name", "e.g. Donald Trump",
     "Search public Wikidata, Wikipedia", "and GitHub candidate records.", 0},
    {"AI web & PDFs", "ai-web", "Name or research topic", "e.g. Donald Trump",
     "Search documents, web and PDFs.", "Get 3-5 sourced key findings.", 0},
    {"IPv4 address", "ipv4", "IPv4 address", "e.g. 8.8.8.8",
     "Network operator, DNS, services", "and public technical records.", 0},
    {"IPv6 address", "ipv6", "IPv6 address", "e.g. 2606:4700:4700::1111",
     "Public IPv6 network records", "and reachable services.", 0},
    {"Website / domain", "website", "Website URL or domain", "e.g. https://example.com",
     "DNS, TLS, hosts, technologies", "and related infrastructure.", 0},
    {"GPS coordinates", "gps", "Latitude, longitude", "e.g. 48.086056, 11.556722",
     "Nearby clinics, restaurants", "and public business contacts.", 0},
    {"Address / place", "address", "Place or address", "e.g. Berlin Alexanderplatz",
     "Nearby facilities, addresses", "and listed business contacts.", 0},
    {"Company", "company", "Company name", "e.g. Siemens",
     "Public records, website, DNS", "and organization links.", 0},
    {"Organization", "organization", "Organization name", "e.g. Wikimedia Foundation",
     "Public organization sources", "and official websites.", 0},
    {"Company number", "registry", "Company registration number", "e.g. HRB 12345",
     "Official register reference.", "Matches need verification.", 0},
    {"Car license plate", "plate", "Vehicle plate", "e.g. B-AB 1234",
     "Format validation only.", "No vehicle-owner lookup.", 0},
    {"Vehicle ID (VIN)", "vin", "Vehicle identification number", "17 letters and digits",
     "Vehicle model and manufacturer", "from public specifications.", 0},
    {"Crypto address", "wallet", "Crypto wallet address", "e.g. 0x123...",
     "Address type and public explorer", "without owner assumptions.", 0},
    {"Network number", "asn", "Autonomous system number", "e.g. AS15169",
     "Public operator and network", "prefix information.", 0},

    {"AI search setup", "ai-status", "AI configuration", "",
     "Check web and model connection.", "Shows setup steps, never secrets.", MF_NOINPUT},
    {"Check tools", "pi-status", "Modules", "",
     "Which extra tools are available", "and which still need setup?", MF_NOINPUT},
    {"Research settings", "pi-case", "Optional case notes", "e.g. research purpose",
     "Setup for separately authorized", "advanced checks. Not required here.", 0},
    {"View connections", "pi-graph", "Connections", "",
     "Relationships and their sources.", "Unverified hints stay marked.", MF_NOINPUT},
    {"View report", "pi-report", "Report", "",
     "Review sourced findings and", "what remains unconfirmed.", MF_NOINPUT},
    {"Import saved report", "person-report", "Report file", "/home/user/Files/report.txt",
     "Load a previously saved report", "from this device.", 0},
};
#define NMODES ((int)(sizeof modes / sizeof modes[0]))

enum { S_MENU, S_INPUT, S_CONFIRM, S_RUN };
static int screen = S_MENU;
static int sel = 0;
static int menu_view = 0; /* first visible menu row */
static int mode_idx = 0;
static char inputs[NMODES][MAXIN + 1];
static int cur[NMODES];   /* text cursor position per mode */
static int cf_third = 0, cf_tos = 0; /* the two statements on the confirmation screen */
static int run_confirmed = 0;        /* hand "confirm" to the backend for this run */
static int view_off = 0;  /* first visible character of the input field */
static int quit = 0;
static int text_seen = 0;

typedef struct { char t[COLS + 1]; unsigned char kind; } Line;
static Line lines[MAXLINES];
static int nlines = 0, scroll_pos = 0, follow = 1;

/* Result views: 0 = live/full scroll, 1 = overview (list of sections),
 * 2 = one section opened from the overview. The overview is an index of
 * everything found, each row a category the d-pad opens. */
enum { RV_FULL, RV_OVERVIEW, RV_SECTION, RV_GROUPS, RV_ITEMS, RV_DETAIL };
static int run_view = RV_FULL;
static int sec_sel = 0, sec_open = 0, sec_view = 0;
static int finished_seen = 0;
#define MAXSEC 128
static int secHead[MAXSEC];
static int nsec = 0;

static void rebuild_sections(void) {
    nsec = 0;
    for (int i = 0; i < nlines && nsec < MAXSEC; i++)
        if (lines[i].kind == 4 && lines[i].t[0] == '#') secHead[nsec++] = i;
}

static void secRange(int i, int *start, int *end) {
    *start = secHead[i];
    *end = (i + 1 < nsec) ? secHead[i + 1] : nlines;
}

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

/* Source-aware hierarchical result browser. */
#include "result_catalog.h"

static void push_result(const char *raw) {
    char m = raw[0];
    const char *rest = raw[0] ? (raw[1] == ' ' ? raw + 2 : raw + 1) : raw;
    got_output = 1;
    catalog_ingest(raw);
    switch (m) {
    case '#':
        if (nlines > 0) add_line("", 0);
        wrap_add('#', rest, 4);
        break;
    case '+': wrap_add('+', rest, 1); break;
    case '-': wrap_add('-', rest, 2); break;
    case '!': wrap_add('!', rest, 3); break;
    case '=': wrap_add('=', rest, 5); break; /* proven: only after a human review */
    case '~': wrap_add('~', rest, 6); break; /* indication */
    case '?': wrap_add('?', rest, 7); break; /* unconfirmed */
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

static int spawn_cli(const char *type, const char *value, const char *extra) {
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
        if (extra && *extra)
            execl(cli_path, cli_path, type, value, extra, (char *)NULL);
        else
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
    /* Modes without a text field pass a placeholder: the backend expects two arguments. */
    if (l == 0) {
        if (!(modes[mode_idx].flags & MF_NOINPUT)) return;
        strcpy(in, "show");
        l = 4;
    }
    stop_child();
    nlines = 0;
    scroll_pos = 0;
    follow = 1;
    catalog_reset();
    inlen = 0;
    finished = 0;
    got_output = 0;
    run_view = RV_FULL;
    finished_seen = 0;
    sec_sel = 0;
    sec_view = 0;
    nsec = 0;
    screen = S_RUN;
    if (spawn_cli(modes[mode_idx].cmd, in, run_confirmed ? "confirm" : NULL) != 0) {
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
    int lo = 0, hi;
    if (screen == S_RUN && run_view == RV_SECTION && nsec > 0) {
        int s, e;
        secRange(sec_open, &s, &e);
        lo = s;
        hi = e - VH;
        if (hi < lo) hi = lo;
    } else {
        hi = nlines > VH ? nlines - VH : 0;
    }
    scroll_pos += d;
    if (scroll_pos < lo) scroll_pos = lo;
    if (scroll_pos > hi) scroll_pos = hi;
    follow = (run_view == RV_FULL && scroll_pos >= hi);
}

static void go_back_from_run(void) {
    stop_child();
    screen = S_MENU;
}

static void menu_sync_view(void);

static void activate(int idx) {
    mode_idx = idx;
    run_confirmed = 0;
    if (modes[idx].flags & MF_NOINPUT) {
        inputs[idx][0] = 0;
        cur[idx] = 0;
        start_run();
        return;
    }
    screen = S_INPUT;
    SDL_StartTextInput();
}

/* An active check never starts straight from the input screen. */
static void request_start(void) {
    if (modes[mode_idx].flags & MF_ACTIVE) {
        const char *in = inputs[mode_idx];
        if (!in[0]) return;
        cf_third = cf_tos = 0;
        screen = S_CONFIRM;
        return;
    }
    run_confirmed = 0;
    start_run();
}

/* ---------- on-screen keyboard ---------- */
enum { K_CHAR, K_BKSP, K_SHIFT, K_SPACE, K_CLEAR };
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
    osk_add(4, 5, 3, ' ', K_SPACE);
    osk_add(4, 8, 1, 0, K_CLEAR);
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
    case K_CLEAR: in_clear(); break;
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
    case S_CONFIRM: screen = S_INPUT; break;
    case S_RUN:
        if (running || run_view==RV_FULL) go_back_from_run();
        else catalog_back();
        break;
    default: break;
    }
}

/* Z goes home; X goes back one level. The old All/Index toggle is removed. */
static void act_z(void) {
    if (screen == S_INPUT) in_move(-1);
    else if (screen == S_CONFIRM) cf_third = !cf_third;
    else if (screen == S_RUN) go_back_from_run();
    else quit = 1;
}
static void act_x(void) {
    if (screen == S_INPUT) { in_move(1); return; }
    if (screen == S_CONFIRM) { cf_tos = !cf_tos; return; }
    if (screen == S_RUN) {
        if (running || run_view == RV_FULL) go_back_from_run();
        else catalog_back();
    }
}

static void act_v(void) {
    if (screen == S_INPUT) {
        /* The system swallows the physical Bksp key (it closes the app), so
         * the step back lives on a button the app actually receives. */
        screen = S_MENU;
    } else if (screen == S_CONFIRM) {
        screen = S_INPUT; /* cancel: nothing was sent */
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
    case S_INPUT: request_start(); break;
    case S_CONFIRM:
        if (cf_third && cf_tos) {
            run_confirmed = 1;
            start_run();
        }
        break;
    case S_RUN:
        if (!running && run_view!=RV_FULL) catalog_open();
        break;
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
        if (s == SDLK_UP) { sel = (sel + NMODES - 1) % NMODES; menu_sync_view(); }
        else if (s == SDLK_DOWN) { sel = (sel + 1) % NMODES; menu_sync_view(); }
        else if (s == SDLK_PAGEUP) { sel = sel > 5 ? sel - 6 : 0; menu_sync_view(); }
        else if (s == SDLK_PAGEDOWN) { sel = sel + 6 < NMODES ? sel + 6 : NMODES - 1; menu_sync_view(); }
        else if (s == SDLK_HOME) { sel = 0; menu_sync_view(); }
        else if (s == SDLK_END) { sel = NMODES - 1; menu_sync_view(); }
        else if (enter) activate(sel);
        else if (s >= SDLK_1 && s <= SDLK_5) { sel = (int)(s - SDLK_1); menu_sync_view(); activate(sel); }
        break;
    case S_CONFIRM:
        if (s == SDLK_ESCAPE) screen = S_INPUT;
        else if (s == SDLK_UP || s == SDLK_LEFT) cf_third = !cf_third;
        else if (s == SDLK_DOWN || s == SDLK_RIGHT) cf_tos = !cf_tos;
        else if (enter && cf_third && cf_tos) { run_confirmed = 1; start_run(); }
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
        if (s == SDLK_ESCAPE) {
            if (running || run_view==RV_FULL) go_back_from_run();
            else catalog_back();
        } else if (s == SDLK_UP) {
            if (run_view==RV_FULL) scroll_by(-1); else catalog_move(-1);
        } else if (s == SDLK_DOWN) {
            if (run_view==RV_FULL) scroll_by(1); else catalog_move(1);
        } else if (enter) {
            if (!running && run_view!=RV_FULL) catalog_open();
        } else if (s == SDLK_PAGEUP) {
            if (run_view==RV_FULL) scroll_by(-(VH-1)); else catalog_move(-(CAT_VISIBLE-1));
        } else if (s == SDLK_PAGEDOWN) {
            if (run_view==RV_FULL) scroll_by(VH-1); else catalog_move(CAT_VISIBLE-1);
        } else if (s == SDLK_HOME) {
            if (run_view==RV_FULL) scroll_by(-MAXLINES); else catalog_move(-MAXLINES);
        } else if (s == SDLK_END) {
            if (run_view==RV_FULL) scroll_by(MAXLINES); else catalog_move(MAXLINES);
        }
        break;
    }
}

#define MENU_Y0 17
#define MENU_P 15
#define MENU_H 13
#define MENU_VIS 6 /* visible menu rows; the list scrolls */
#define CF_Y0 54   /* first statement on the confirmation screen */
#define CF_GAP 27  /* distance to the second statement */

/* Keep the selected entry inside the visible window. */
static void menu_sync_view(void) {
    if (sel < menu_view) menu_view = sel;
    if (sel >= menu_view + MENU_VIS) menu_view = sel - MENU_VIS + 1;
    if (menu_view > NMODES - MENU_VIS) menu_view = NMODES - MENU_VIS;
    if (menu_view < 0) menu_view = 0;
}

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
        int row = (y - MENU_Y0 + 2) / MENU_P;
        int i = menu_view + row;
        if (y >= MENU_Y0 - 2 && row >= 0 && row < MENU_VIS && i < NMODES) {
            sel = i;
            menu_sync_view();
            activate(sel);
        }
    } else if (screen == S_CONFIRM) {
        if (y >= CF_Y0 && y < CF_Y0 + CH + 4) cf_third = !cf_third;
        else if (y >= CF_Y0 + CF_GAP && y < CF_Y0 + CF_GAP + CH + 4) cf_tos = !cf_tos;
    } else if (screen == S_RUN && run_view != RV_FULL && y >= 17 && y < 17+CAT_ROW_H*CAT_VISIBLE) {
        catalog_click_row((y-17)/CAT_ROW_H);
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
    if (screen == S_RUN && run_view != RV_FULL) catalog_move(-dy*2);
    else if (screen == S_RUN) scroll_by(-dy * 3);
    else if (screen == S_MENU) {
        sel = (sel - dy + NMODES * 8) % NMODES;
        menu_sync_view();
    }
}

/* ---------- screens ---------- */
static void draw_menu(void) {
    char right[24];
    snprintf(right, sizeof right, "%d/%d", sel + 1, NMODES);
    title(right);
    for (int r = 0; r < MENU_VIS; r++) {
        int i = menu_view + r;
        if (i >= NMODES) break;
        int y = MENU_Y0 + r * MENU_P;
        int on = (i == sel);
        pill(6, y, W - 14, MENU_H, on ? C_INK : C_PILL);
        text_px(13, y + 3, modes[i].label, on ? C_LIGHT : C_INK);
        /* mark what contacts third parties, so it is visible before opening */
        if (modes[i].flags & MF_ACTIVE)
            text_px(W - 30, y + 3, "!", on ? C_LIGHT : C_RED);
        if (on) text_px(W - 21, y + 3, ">", C_LIGHT);
    }
    if (NMODES > MENU_VIS) {
        int track = MENU_VIS * MENU_P;
        int th = track * MENU_VIS / NMODES;
        if (th < 6) th = 6;
        int mx = NMODES - MENU_VIS;
        int ty = MENU_Y0 + (track - th) * menu_view / (mx > 0 ? mx : 1);
        rect(W - 4, MENU_Y0, 1, track, C_FIELD);
        rect(W - 5, ty, 3, th, C_INK);
    }
    text_px(8, 111, modes[sel].d1, C_SOFT);
    text_px(8, 120, modes[sel].d2, C_SOFT);
    softkeys("Exit", NULL, NULL, "Open");
}

/* Confirmation of an active check: the identifier is shown again and both statements
 * have to be ticked. Z toggles the first, X the second, B starts, V cancels. */
static void draw_confirm(void) {
    title("Active check");
    const Mode *m = &modes[mode_idx];
    pill(4, 16, W - 8, 11, C_FIELD);
    text_bold(8, 17, "Contacts third parties", C_INK);
    text_px(8, 29, "Modules:", C_SOFT);
    text_px(8 + 9 * CW, 29, m->label, C_INK);
    text_px(8, 40, m->prompt, C_SOFT);
    char v[COLS + 1];
    snprintf(v, sizeof v, "%s", inputs[mode_idx]);
    text_bold(8 + (int)(strlen(m->prompt) + 1) * CW, 40, v, C_INK);

    const char *l1a = "The query can be visible to";
    const char *l1b = "the person (e.g. notices).";
    const char *l2a = "Terms of service are kept;";
    const char *l2b = "it is within the purpose.";
    for (int i = 0; i < 2; i++) {
        int y = CF_Y0 + i * CF_GAP;
        int on = i == 0 ? cf_third : cf_tos;
        pill(4, y, 11, 11, on ? C_INK : C_PILL);
        if (on) {
            rect(7, y + 6, 2, 2, C_LIGHT);
            rect(9, y + 4, 2, 2, C_LIGHT);
            rect(11, y + 2, 2, 2, C_LIGHT);
        }
        text_px(19, y + 1, i == 0 ? l1a : l2a, C_INK);
        text_px(19, y + 11, i == 0 ? l1b : l2b, C_INK);
        text_px(W - 7 * CW, y + 1, i == 0 ? "[Z]" : "[X]", C_SOFT);
    }
    int ready = cf_third && cf_tos;
    text_px(8, 111, ready ? "Both confirmed - B starts the query." : "Tick both with Z and X.",
            ready ? C_INK : C_SOFT);
    text_px(8, 120, "Nothing has been sent yet.", C_SOFT);
    softkeys("Tick 1", "Tick 2", "Cancel", ready ? "Start" : "...");
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
            case K_CLEAR: lab = "clr"; break;
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
    softkeys("<", ">", "Back", "Start");
}

/* draw_lines renders VH rows of the result list, limited to [from, to), with a
 * scrollbar. Shared by the full view and a single opened section. */
static void draw_lines(int from, int to) {
    for (int r = 0; r < VH; r++) {
        int i = scroll_pos + r;
        if (i >= to) break;
        if (i < from) continue;
        int y = HDR + r * CH + 1;
        const Line *ln = &lines[i];
        char mk = ln->t[0];
        if (ln->kind == 4) {
            pill(4, y - 1, W - 12, CH + 1, C_FIELD);
            text_bold(10, y, ln->t + 2, C_INK);
            continue;
        }
        Color tc = C_INK;
        switch (ln->kind) {
        case 2: tc = C_SOFT; break;
        case 3: tc = C_RED; break;
        case 5: tc = C_PROVEN; break;
        case 6: tc = C_INDIC; break;
        case 7: tc = C_UNCONF; break;
        default: break;
        }
        if (mk == '+') rect(5, y + 2, 3, 3, C_GREEN);
        else if (mk == '-') rect(5, y + 2, 3, 3, C_SOFT);
        else if (mk == '!') rect(5, y + 2, 3, 3, C_RED);
        else if (mk == '=') { rect(4, y + 1, 5, 5, C_PROVEN); rect(5, y + 2, 3, 3, C_LIGHT); }
        else if (mk == '~') rect(4, y + 2, 5, 3, C_INDIC);
        else if (mk == '?') rect(6, y + 3, 2, 2, C_UNCONF); /* faint dot: weakest level */
        /* proven findings are the only ones drawn bold */
        if (ln->kind == 5) text_bold(12, y, ln->t + 2, tc);
        else text_px(12, y, ln->t + 2, tc);
    }
    int total = to - from;
    if (total > VH) {
        int track = VH * CH;
        int th = track * VH / total;
        if (th < 6) th = 6;
        int mx = total - VH;
        int ty = HDR + (track - th) * (scroll_pos - from) / (mx > 0 ? mx : 1);
        rect(W - 3, HDR, 1, track, C_FIELD);
        rect(W - 4, ty, 3, th, C_INK);
    }
}

/* Worst-severity dot for a section's lines: red warning, else green finding. */
static void sev_dot(int x, int y, int st, int en) {
    int bang = 0, ok = 0, proven = 0;
    for (int i = st; i < en; i++) {
        char m = lines[i].t[0];
        if (m == '!') bang = 1;
        else if (m == '=') proven = 1;
        else if (m == '+' || m == '~') ok = 1;
    }
    if (proven) {
        rect(x - 1, y - 1, 5, 5, C_PROVEN);
        rect(x, y, 3, 3, C_LIGHT);
        return;
    }
    rect(x, y, 3, 3, bang ? C_RED : (ok ? C_GREEN : C_SOFT));
}

static void draw_full(void) {
    static const char spin[] = "|/-\\";
    char right[24];
    if (running) snprintf(right, sizeof right, "%c Running", spin[(SDL_GetTicks() / 120) % 4]);
    else snprintf(right, sizeof right, "All  %d lines", nlines);
    title(right);
    draw_lines(0, nlines);
    softkeys("Home", "Back", running ? "Stop" : "Again", NULL);
}

static void draw_section(void) {
    int st, en;
    secRange(sec_open, &st, &en);
    char right[24];
    snprintf(right, sizeof right, "%d/%d", sec_open + 1, nsec);
    title(right);
    draw_lines(st, en);
    softkeys("Exit", "Back", "Refresh", "Again");
}

static void draw_overview(void) {
    title("Overview");
    if (nsec == 0) {
        text_px(12, HDR + 4, "No results", C_SOFT);
        softkeys("Exit", "All", running ? "Stop" : "Refresh", "Again");
        return;
    }
    if (sec_sel < sec_view) sec_view = sec_sel;
    if (sec_sel >= sec_view + VH) sec_view = sec_sel - VH + 1;
    for (int r = 0; r < VH; r++) {
        int i = sec_view + r;
        if (i >= nsec) break;
        int y = HDR + r * CH + 1;
        int st, en;
        secRange(i, &st, &en);
        int sel = (i == sec_sel);
        if (sel) pill(2, y - 1, W - 6, CH + 1, C_INK);
        sev_dot(6, y + 2, st + 1, en);
        text_px(12, y, lines[st].t + 2, sel ? C_LIGHT : C_INK);
        int plus = 0, bang = 0;
        for (int k = st + 1; k < en; k++) {
            char m = lines[k].t[0];
            if (m == '+' || m == '=' || m == '~' || m == '?') plus++;
            else if (m == '!') bang++;
        }
        char cnt[16];
        if (bang) snprintf(cnt, sizeof cnt, "+%d !%d", plus, bang);
        else snprintf(cnt, sizeof cnt, "%d", en - st - 1);
        int cw = (int)strlen(cnt) * CW;
        text_px(W - 8 - cw, y, cnt, bang ? C_RED : (sel ? C_LIGHT : C_SOFT));
    }
    if (nsec > VH) {
        int track = VH * CH;
        int th = track * VH / nsec;
        if (th < 6) th = 6;
        int mx = nsec - VH;
        int ty = HDR + (track - th) * sec_view / (mx > 0 ? mx : 1);
        rect(W - 3, HDR, 1, track, C_FIELD);
        rect(W - 4, ty, 3, th, C_INK);
    }
    softkeys("Exit", "All", "Refresh", "Again");
}

static void draw_run(void) {
    /* During the search, live output remains available; when finished,
     * enter the categorized browser automatically. */
    if (finished && !finished_seen) {
        finished_seen = 1;
        run_view = RV_OVERVIEW;
        cat_sel = cat_top = 0;
    }
    if (run_view == RV_FULL) draw_full();
    else catalog_draw();
}

static void render(void) {
    SDL_SetRenderDrawColor(ren, C_BG.r, C_BG.g, C_BG.b, 255);
    SDL_RenderClear(ren);
    switch (screen) {
    case S_MENU: draw_menu(); break;
    case S_INPUT: draw_input(); break;
    case S_CONFIRM: draw_confirm(); break;
    case S_RUN: draw_run(); break;
    }
    SDL_RenderPresent(ren);
}

/* ---------- self test ----------
 * Checks the state machine without a display: menu scrolling, the confirmation step for
 * active checks, and the marker-to-row mapping. Run with "osint-ui --selftest"; it is also
 * run by the build workflow, so a regression in the key handling fails the build.
 */
#define T_CHECK(cond, ...)                                                                        \
    do {                                                                                          \
        if (!(cond)) {                                                                            \
            fprintf(stderr, "FAIL %s:%d: ", __func__, __LINE__);                                  \
            fprintf(stderr, __VA_ARGS__);                                                         \
            fprintf(stderr, "\n");                                                                \
            t_fail++;                                                                             \
        } else                                                                                    \
            t_ok++;                                                                               \
    } while (0)

static int t_ok = 0, t_fail = 0;

static void t_reset(void) {
    screen = S_MENU;
    sel = 0;
    menu_view = 0;
    mode_idx = 0;
    run_confirmed = 0;
    cf_third = cf_tos = 0;
    nlines = 0;
    catalog_reset();
    nsec = 0;
    running = 0;
    finished = 0;
    for (int i = 0; i < NMODES; i++) {
        inputs[i][0] = 0;
        cur[i] = 0;
    }
}

static void t_menu(void) {
    t_reset();
    T_CHECK(NMODES >= 14, "expected at least 14 modes, got %d", NMODES);
    /* First six are input identifiers; legacy workflows remain available below. */
    const char *first6[] = {"combo-phone", "combo-email", "combo-username", "person-name", "ai-web", "ipv4"};
    for (int i = 0; i < 6; i++)
        T_CHECK(strcmp(modes[i].cmd, first6[i]) == 0, "mode %d is %s, expected %s", i, modes[i].cmd, first6[i]);
    /* Original CLI paths are preserved in Go, but duplicates do not clutter the menu. */
    for (int i=0;i<NMODES;i++) {
        T_CHECK(strcmp(modes[i].label, "IP: original")!=0, "confusing old IP menu label");
        T_CHECK(strcmp(modes[i].label, "Vendor: name")!=0, "confusing vendor menu label");
    }
    /* every mode reachable with the d-pad, and the selection stays visible */
    for (int i = 0; i < NMODES; i++) {
        T_CHECK(sel == i, "selection %d, expected %d", sel, i);
        T_CHECK(sel >= menu_view && sel < menu_view + MENU_VIS, "entry %d outside the window (view %d)", sel, menu_view);
        T_CHECK(menu_view >= 0 && menu_view <= NMODES - MENU_VIS, "view %d out of range", menu_view);
        if (i < NMODES - 1) {
            sel = (sel + 1) % NMODES;
            menu_sync_view();
        }
    }
    /* wrap around to the top */
    sel = (sel + 1) % NMODES;
    menu_sync_view();
    T_CHECK(sel == 0 && menu_view == 0, "wrap around failed (sel %d, view %d)", sel, menu_view);
    /* every mode has a label and a description */
    for (int i = 0; i < NMODES; i++) {
        T_CHECK(modes[i].label && modes[i].label[0], "mode %d without label", i);
        T_CHECK(modes[i].d1 && modes[i].d1[0], "mode %d without description", i);
        T_CHECK(strlen(modes[i].label) <= 34, "label of mode %d too long for the panel", i);
        T_CHECK(strlen(modes[i].d1) <= 40 && strlen(modes[i].d2) <= 40, "description of mode %d too long", i);
    }
}

static int t_mode_by_cmd(const char *cmd) {
    for (int i = 0; i < NMODES; i++)
        if (strcmp(modes[i].cmd, cmd) == 0) return i;
    return -1;
}

static void t_instant_search(void) {
    t_reset();
    const char *public_queries[]={"combo-phone","combo-email","combo-username","person-name","ai-web",
        "company","website","address","gps"};
    for (size_t i=0;i<sizeof public_queries/sizeof public_queries[0];i++) {
        int idx=t_mode_by_cmd(public_queries[i]);
        T_CHECK(idx>=0, "missing public input mode %s",public_queries[i]);
        if (idx<0) continue;
        T_CHECK(!(modes[idx].flags & MF_ACTIVE), "unnecessary confirmation for %s",public_queries[i]);
        mode_idx=idx;
        screen=S_INPUT;
        strcpy(inputs[idx],"example.com");
        cli_path="/bin/true";
        request_start();
        T_CHECK(screen==S_RUN, "public search %s did not start directly",public_queries[i]);
        stop_child();
        screen=S_MENU;
    }
    t_reset();
    mode_idx=t_mode_by_cmd("combo-username");
    screen=S_INPUT;
    request_start();
    T_CHECK(screen==S_INPUT,"empty input must not start a query");
}


static void t_noinput(void) {
    t_reset();
    int idx = t_mode_by_cmd("pi-status");
    T_CHECK(idx >= 0 && (modes[idx].flags & MF_NOINPUT), "pi-status must need no input");
    cli_path = "/bin/true";
    sel = idx;
    activate(idx);
    T_CHECK(screen == S_RUN, "a mode without input must run straight away, got %d", screen);
    T_CHECK(strcmp(inputs[idx], "show") == 0, "placeholder value missing: '%s'", inputs[idx]);
    stop_child();
}

static void t_markers(void) {
    t_reset();
    struct { const char *line; int kind; char marker; } cases[] = {
        {"+ found something", 1, '+'},
        {"- nothing there", 2, '-'},
        {"! careful", 3, '!'},
        {"= proven by the source", 5, '='},
        {"~ an indication only", 6, '~'},
        {"? unconfirmed hint", 7, '?'},
        {"i plain info", 0, ' '},
    };
    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        nlines = 0;
        push_result(cases[i].line);
        T_CHECK(nlines == 1, "line %zu produced %d rows", i, nlines);
        T_CHECK(lines[0].kind == cases[i].kind, "line %zu: kind %d, expected %d", i, lines[0].kind, cases[i].kind);
        T_CHECK(lines[0].t[0] == cases[i].marker, "line %zu: marker '%c', expected '%c'", i, lines[0].t[0],
                cases[i].marker);
    }
    /* section headings build the index, evidence rows are counted as hits */
    nlines = 0;
    push_result("# Person modules");
    push_result("~ an indication");
    push_result("= proven");
    push_result("# Summary");
    push_result("+ ok");
    rebuild_sections();
    T_CHECK(nsec == 2, "expected 2 sections, got %d", nsec);
    int st, en;
    secRange(0, &st, &en);
    T_CHECK(lines[st].kind == 4, "a section must start with a heading");
    /* long lines wrap instead of being cut off */
    nlines = 0;
    char longline[400];
    memset(longline, 'a', sizeof longline - 1);
    longline[sizeof longline - 1] = 0;
    longline[0] = '~';
    longline[1] = ' ';
    push_result(longline);
    T_CHECK(nlines > 1, "a long line must wrap, got %d rows", nlines);
    for (int i = 0; i < nlines; i++)
        T_CHECK(strlen(lines[i].t) <= COLS, "row %d longer than the panel", i);
}

static void t_input_editing(void) {
    t_reset();
    mode_idx = 1; /* email */
    screen = S_INPUT;
    append_input("name@example.com");
    T_CHECK(strcmp(inputs[1], "name@example.com") == 0, "input is '%s'", inputs[1]);
    in_move(-4);
    in_insert('X');
    T_CHECK(strcmp(inputs[1], "name@exampleX.com") == 0, "cursor insert failed: '%s'", inputs[1]);
    in_delete();
    T_CHECK(strcmp(inputs[1], "name@example.com") == 0, "delete failed: '%s'", inputs[1]);
    in_clear();
    T_CHECK(inputs[1][0] == 0, "clear failed");
    /* the field must not overflow */
    for (int i = 0; i < MAXIN + 50; i++) in_insert('a');
    T_CHECK((int)strlen(inputs[1]) == MAXIN, "field length %zu, expected %d", strlen(inputs[1]), MAXIN);
    /* backspace in an empty field steps back to the menu, it never closes the app */
    in_clear();
    act_back();
    T_CHECK(screen == S_MENU, "step back failed");
    T_CHECK(quit == 0, "the app must not close here");
}

/* Large result sets must not overflow or slow the panel down: the list is capped and the
 * backend output is consumed line by line as it arrives. */
static void t_large_output(void) {
    t_reset();
    for (int i = 0; i < MAXLINES + 500; i++) {
        char b[80];
        snprintf(b, sizeof b, "~ finding number %d", i);
        push_result(b);
    }
    T_CHECK(nlines == MAXLINES, "line buffer is %d, expected the cap %d", nlines, MAXLINES);
    T_CHECK(scroll_pos <= nlines, "scroll position %d beyond the list", scroll_pos);
    /* the index stays usable as well */
    nlines = 0;
    for (int i = 0; i < MAXSEC + 20; i++) {
        char b[80];
        snprintf(b, sizeof b, "# section %d", i);
        push_result(b);
        push_result("+ one hit");
    }
    rebuild_sections();
    T_CHECK(nsec <= MAXSEC, "section index is %d, expected at most %d", nsec, MAXSEC);
    int st, en;
    secRange(nsec - 1, &st, &en);
    T_CHECK(st >= 0 && en <= nlines && st < en, "last section range %d..%d invalid", st, en);
}

/* Regression tests for the new category -> platform -> finding -> detail flow. */
static void t_catalog_browser(void) {
    t_reset();
    push_result("# Public name search");
    push_result("+ Donald Trump (Q22686)");
    push_result("~ X / Twitter: https://x.com/realDonaldTrump");
    push_result("i Source: https://www.wikidata.org/wiki/Q22686");
    push_result("~ X / Twitter: https://x.com/realDonaldTrump");
    push_result("~ GitHub: https://github.com/example_public");
    push_result("! Provider rate limit");
    T_CHECK(catalog_n==4,"expected 4 unique records, got %d",catalog_n);
    T_CHECK(catalog_group_count(GR_X)==1,"Twitter duplicates were not merged");
    T_CHECK(catalog_group_count(GR_GITHUB)==1,"GitHub group missing");
    T_CHECK(catalog_category_count(CAT_PERSON)==1,"Identity record missing");
    T_CHECK(catalog_category_count(CAT_PROFILES)==2,"Profile category count wrong");
    T_CHECK(catalog_category_count(CAT_OTHER)==1,"Warnings should remain visible");
    T_CHECK(catalog[1].repeats==2,"duplicate source count not preserved");
    T_CHECK(catalog[1].source[0]!=0,"source was not attached to the record");

    screen=S_RUN;
    run_view=RV_OVERVIEW;
    for (int i=0;i<catalog_category_total();i++)
        if (catalog_category_at(i)==CAT_PROFILES) cat_sel=i;
    catalog_open();
    T_CHECK(run_view==RV_GROUPS,"categories did not open subgroup menu");
    for (int i=0;i<catalog_group_total(CAT_PROFILES);i++)
        if (catalog_group_at(CAT_PROFILES,i)==GR_X) group_sel=i;
    catalog_open();
    T_CHECK(run_view==RV_ITEMS,"subgroup did not open findings");
    catalog_open();
    T_CHECK(run_view==RV_DETAIL,"finding did not open source/details");
    act_x();
    T_CHECK(run_view==RV_ITEMS,"X should return from detail to findings");
    act_x();
    T_CHECK(run_view==RV_GROUPS,"X should return to group list");
    act_x();
    T_CHECK(run_view==RV_OVERVIEW,"X should return to categories");
    act_x();
    T_CHECK(screen==S_MENU,"X should return to start menu from root");
    screen=S_RUN;
    run_view=RV_OVERVIEW;
    act_z();
    T_CHECK(screen==S_MENU && quit==0,"Z Home must not quit app");
}

/* Verify that actionable OSM POI output becomes meaningful subcategories. */
static void t_geo_categories(void) {
    t_reset();
    push_result("# Nearby facilities and businesses (500m)");
    push_result("+ Clinic: Beispiel Klinik (12m)");
    push_result("i Source: https://www.openstreetmap.org/way/101");
    push_result("+ Restaurant: Bistro Test (45m)");
    push_result("+ Business phone: +49 89 123456");
    push_result("+ Business email: info@klinik.example");
    push_result("+ Business website: https://klinik.example");
    push_result("+ Public DNS: klinik.example -> 192.0.2.1");
    T_CHECK(catalog_group_count(GR_HEALTH)==1,
            "clinic must be in healthcare group");
    T_CHECK(catalog_group_count(GR_FOOD)==1,
            "restaurant must be in food group");
    T_CHECK(catalog_group_count(GR_PHONE)==1,
            "listed business phone missing from contacts");
    T_CHECK(catalog_group_count(GR_EMAIL)==1,
            "listed business email missing from contacts");
    T_CHECK(catalog_group_count(GR_ORGWEB)==1,
            "listed business website missing from organizations");
    T_CHECK(catalog_group_count(GR_DNS)==1,
            "DNS pivot missing from technical results");
    T_CHECK(catalog_category_count(CAT_PLACES)==2,
            "clinic + restaurant should be listed under Places");
}

static int selftest(void) {
    t_menu();
    t_large_output();
    t_instant_search();
    t_noinput();
    t_markers();
    t_input_editing();
    t_catalog_browser();
    t_geo_categories();
    printf("osint-ui selftest: %d checks ok, %d failed\n", t_ok, t_fail);
    return t_fail == 0 ? 0 : 1;
}

/* ---------- screenshot ----------
 * "osint-ui --screenshot <dir>" renders every screen once into <dir> as BMP files, using the offscreen
 * driver. Used to review the panel layout without a device.
 */
static int screenshot(const char *dir) {
    SDL_SetHint(SDL_HINT_RENDER_DRIVER, "software");
    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
        return 1;
    }
    win = SDL_CreateWindow("OSINT", 0, 0, W, H, SDL_WINDOW_HIDDEN);
    ren = win ? SDL_CreateRenderer(win, -1, SDL_RENDERER_SOFTWARE) : NULL;
    if (!ren) {
        fprintf(stderr, "no renderer: %s\n", SDL_GetError());
        return 1;
    }
    SDL_RenderSetLogicalSize(ren, W, H);
    build_atlas();
    if (!atlas) return 1;

    struct { const char *name; int scr; } shots[] = {
        {"1-menu-top", S_MENU}, {"2-menu-person", S_MENU}, {"3-input", S_INPUT},
        {"4-confirm", S_CONFIRM}, {"5-confirm-ready", S_CONFIRM}, {"6-results", S_RUN},
        {"7-overview", S_RUN},
    };
    for (size_t i = 0; i < sizeof shots / sizeof shots[0]; i++) {
        t_reset();
        screen = shots[i].scr;
        if (strcmp(shots[i].name, "2-menu-person") == 0) {
            sel = 7; /* Person: username */
            menu_sync_view();
        } else if (shots[i].scr == S_INPUT) {
            mode_idx = 8; /* Person: email */
            strcpy(inputs[mode_idx], "erika@example.org");
            cur[mode_idx] = (int)strlen(inputs[mode_idx]);
        } else if (shots[i].scr == S_CONFIRM) {
            mode_idx = 7;
            strcpy(inputs[mode_idx], "jdoe");
            if (strcmp(shots[i].name, "5-confirm-ready") == 0) cf_third = cf_tos = 1;
        } else if (shots[i].scr == S_RUN) {
            push_result("# Person research: username");
            push_result("i Case: Device research (purpose valid until 2026-11-10)");
            push_result("i Sherlock: active check started (contacts third parties)");
            push_result("~ Profile \"jdoe\" on GitHub (per Sherlock)");
            push_result("i     https://github.com/jdoe");
            push_result("i     same handle only - no proof of the same person");
            push_result("= Confirmed: profile named by the source itself");
            push_result("? Hint: same handle on 2 platforms");
            push_result("- Pipl: needs an API key");
            push_result("! Spokeo: rate limit reached (HTTP 429)");
            push_result("# Combined results (3 items)");
            push_result("i Proven 1 | indication 1 | unconfirmed 1");
            finished = 1;
            rebuild_sections();
            if (strcmp(shots[i].name, "7-overview") == 0) {
                run_view = RV_OVERVIEW;
                sec_sel = 0;
            } else {
                run_view = RV_FULL;
                finished_seen = 1; /* otherwise draw_run switches to the overview */
                scroll_pos = 0;
                follow = 0;
            }
        }
        render();
        SDL_Surface *sf = SDL_CreateRGBSurfaceWithFormat(0, W, H, 32, SDL_PIXELFORMAT_ARGB8888);
        if (!sf) continue;
        if (SDL_RenderReadPixels(ren, NULL, SDL_PIXELFORMAT_ARGB8888, sf->pixels, sf->pitch) == 0) {
            char path[512];
            snprintf(path, sizeof path, "%s/%s.bmp", dir, shots[i].name);
            if (SDL_SaveBMP(sf, path) == 0) printf("wrote %s\n", path);
            else fprintf(stderr, "SDL_SaveBMP: %s\n", SDL_GetError());
        } else {
            fprintf(stderr, "SDL_RenderReadPixels: %s\n", SDL_GetError());
        }
        SDL_FreeSurface(sf);
    }
    SDL_DestroyTexture(atlas);
    SDL_DestroyRenderer(ren);
    SDL_DestroyWindow(win);
    SDL_Quit();
    return 0;
}

int main(int argc, char **argv) {
    if (argc > 2 && strcmp(argv[1], "--screenshot") == 0) {
        osk_init();
        return screenshot(argv[2]);
    }
    if (argc > 1 && strcmp(argv[1], "--selftest") == 0) {
        osk_init();
        return selftest();
    }
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
