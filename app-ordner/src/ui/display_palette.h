/*
 * display_palette.h - single source of truth for every OSINT SDL2 UI color.
 *
 * Flipper One emulator: SDL RGB is converted to luminance (0..255) and
 * ONLY THEN tinted orange by the device. To get system-bright orange, draw
 * WHITE (255/255/255), not RGB orange.
 *
 * Role semantics:
 *   background/light surfaces: 255, white
 *   ordinary text, borders, markers, selected background: 0, black
 *   selected text: 255, white
 *   secondary TEXT ONLY: neutral grays (not brown or orange).
 *
 * Do not draw RGB color accents here. The OS owns the orange tint.
 * This file is included once after typedef struct Color in osint-ui.c.
 */
#ifndef OSINT_DISPLAY_PALETTE_H
#define OSINT_DISPLAY_PALETTE_H

static const Color C_BG     = {255, 255, 255}; /* main page and clear */
static const Color C_INK    = {  0,   0,   0}; /* text, borders, selected row */
static const Color C_LIGHT  = {255, 255, 255}; /* inverse selected-row text */
static const Color C_PILL   = {255, 255, 255}; /* ordinary buttons and rows */
static const Color C_FIELD  = {255, 255, 255}; /* inputs and other light panels */
static const Color C_SOFT   = { 96,  96,  96}; /* secondary text / disabled */
static const Color C_GREEN  = {  0,   0,   0}; /* status markers use SHAPES, not colors */
static const Color C_RED    = {  0,   0,   0}; /* warnings use ! symbol */
static const Color C_PROVEN = {  0,   0,   0}; /* proven = mark with white inset */
static const Color C_INDIC  = { 80,  80,  80}; /* indication = medium glyph */
static const Color C_UNCONF = {128, 128, 128}; /* unconfirmed = faint glyph */

#endif /* OSINT_DISPLAY_PALETTE_H */
