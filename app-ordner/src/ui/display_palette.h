/*
 * display_palette.h - single source of truth for every OSINT SDL2 UI color
 * (from the 2.0.2 grayscale line, merged in 2.3.0).
 *
 * The Flipper One panel converts SDL RGB to luminance (0..255) and only
 * then tints it orange. To get the bright system orange, draw WHITE, not
 * RGB orange; RGB orange ends up as a muddy mid-tone.
 *
 * Roles:
 *   pages and button bodies: 255 (white)
 *   text, 1px borders, markers, selected background: 0 (black)
 *   selected text: 255 (white)
 *   secondary text and scrollbar tracks only: neutral gray
 *
 * Status is shown by SHAPE (filled square, hollow square, "!"), never by
 * color. Included once, right after the Color typedef in osint-ui.c.
 */
#ifndef OSINT_DISPLAY_PALETTE_H
#define OSINT_DISPLAY_PALETTE_H

static const Color C_BG = {255, 255, 255};    /* page / clear */
static const Color C_INK = {0, 0, 0};         /* text, borders, selected row */
static const Color C_LIGHT = {255, 255, 255}; /* text on a selected (black) row */
static const Color C_PILL = {255, 255, 255};  /* button bodies */
static const Color C_FIELD = {255, 255, 255}; /* text field and light panels */
static const Color C_SOFT = {96, 96, 96};     /* secondary text, disabled, tracks */

#endif /* OSINT_DISPLAY_PALETTE_H */
