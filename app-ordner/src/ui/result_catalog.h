/*
 * result_catalog.h - Flipper One OSINT 1.4
 * A source-aware, bounded, hierarchical result browser for the 256x144 screen.
 * Included once by osint-ui.c after the line buffer and drawing primitives.
 *
 * Category -> platform/topic -> unique finding -> evidence detail.
 * The CLI output remains unchanged; no data is downloaded by this view.
 */
#ifndef OSINT_RESULT_CATALOG_H
#define OSINT_RESULT_CATALOG_H

#include <ctype.h>

#define CAT_MAX_ITEMS 1600
#define CAT_VISIBLE 8
#define CAT_ROW_H 13 /* one pixel of white space between 12px cards */

enum {
    CAT_AI, CAT_PERSON, CAT_CONTACT, CAT_PROFILES, CAT_PLACES, CAT_ORGS, CAT_TECH,
    CAT_DOCS, CAT_OTHER, CAT_NUM
};
static const char *const cat_titles[CAT_NUM] = {
    "AI key findings", "Person & identity", "Contact details", "Profiles & accounts",
    "Places & maps", "Organizations", "Network & services",
    "Documents & sources", "Other / warnings"
};
enum {
    GR_AI_POINTS, GR_IDENT, GR_WORK, GR_PHONE, GR_EMAIL,
    GR_X, GR_GITHUB, GR_INSTAGRAM, GR_FACEBOOK, GR_REDDIT, GR_SOCIAL,
    GR_COORD, GR_MAP, GR_PLACE, GR_HEALTH, GR_FOOD, GR_SHOPS,
    GR_BUSINESS, GR_ORGWEB,
    GR_IP, GR_DNS, GR_SERVICES, GR_SECURITY, GR_TECH,
    GR_WIKI, GR_DOCUMENT, GR_SOURCE,
    GR_WARNING, GR_MISC, GR_NUM
};
static const char *const group_titles[GR_NUM] = {
    "Important findings", "Names & identities", "Work & education", "Phone numbers", "Email addresses",
    "X / Twitter", "GitHub", "Instagram", "Facebook", "Reddit",
    "Other social accounts", "Coordinates", "Maps & locations", "Places",
    "Clinics & healthcare", "Restaurants & cafes", "Shops & services",
    "Companies & groups", "Official websites",
    "IP addresses & ASN", "DNS & domains", "Services & ports", "TLS & security",
    "Other technical data", "Wikidata / Wikipedia", "Reports & documents",
    "Other references", "Warnings", "Other findings"
};
static const unsigned char group_cat[GR_NUM] = {
    CAT_AI,CAT_PERSON,CAT_PERSON,CAT_CONTACT,CAT_CONTACT,
    CAT_PROFILES,CAT_PROFILES,CAT_PROFILES,CAT_PROFILES,CAT_PROFILES,CAT_PROFILES,
    CAT_PLACES,CAT_PLACES,CAT_PLACES,CAT_PLACES,CAT_PLACES,CAT_PLACES,
    CAT_ORGS,CAT_ORGS,
    CAT_TECH,CAT_TECH,CAT_TECH,CAT_TECH,CAT_TECH,
    CAT_DOCS,CAT_DOCS,CAT_DOCS,CAT_OTHER,CAT_OTHER
};

typedef struct {
    unsigned char group;
    char mark;
    unsigned short repeats;
    char label[216];
    char key[192];
    char section[64];
    char source[174];
    char excerpt[300];
} CatalogItem;

static CatalogItem catalog[CAT_MAX_ITEMS];
static int catalog_n = 0;
static char catalog_section[64];
static int catalog_last = -1;
static int cat_sel = 0, group_sel = 0, item_sel = 0;
static int cat_top = 0, group_top = 0, item_top = 0, detail_top = 0;

static int catalog_has(const char *s, const char *needle) {
    return s && needle && strcasestr(s, needle) != NULL;
}
static int catalog_group(const char *s, const char *section, char marker) {
    if (catalog_has(section,"AI key findings") && catalog_has(s,"AI point")) return GR_AI_POINTS;
    if (marker == '!') return GR_WARNING;
    /* Strong platform/domain patterns take precedence over generic words. */
    if (catalog_has(s,"twitter") || catalog_has(s,"x.com/")) return GR_X;
    if (catalog_has(s,"github") || catalog_has(s,"gist.github.com/")) return GR_GITHUB;
    if (catalog_has(s,"instagram")) return GR_INSTAGRAM;
    if (catalog_has(s,"facebook")) return GR_FACEBOOK;
    if (catalog_has(s,"reddit")) return GR_REDDIT;
    if (catalog_has(s,"profile") || catalog_has(s,"account:") ||
        catalog_has(s,"username") || catalog_has(s,"handle:") ||
        catalog_has(section,"account candidates") ||
        catalog_has(section,"username check")) return GR_SOCIAL;
    if (catalog_has(s,"phone") || catalog_has(s,"telephone") ||
        catalog_has(s,"tel:") || catalog_has(s,"number: +")) return GR_PHONE;
    if (catalog_has(s,"email") || catalog_has(s,"mailto:") ||
        (strchr(s,'@') && strchr(s,'.'))) return GR_EMAIL;
    if (catalog_has(s,"wikidata") || catalog_has(s,"wikipedia") ||
        catalog_has(section,"wikipedia")) return GR_WIKI;
    if (catalog_has(s,"report") || catalog_has(s,"document") ||
        catalog_has(s,"article") || catalog_has(s,"repository")) return GR_DOCUMENT;
    if (catalog_has(s,"source:") || catalog_has(s,"reference:")) return GR_SOURCE;
    if (catalog_has(s,"coordinate") || catalog_has(s,"latitude") ||
        catalog_has(s,"longitude") || catalog_has(s,"gps")) return GR_COORD;
    if (catalog_has(s,"openstreetmap") || catalog_has(s,"osm") ||
        catalog_has(s,"map:")) return GR_MAP;
    if (catalog_has(s,"clinic:") || catalog_has(s,"hospital:") ||
        catalog_has(s,"healthcare:") || catalog_has(s,"pharmacy:")) return GR_HEALTH;
    if (catalog_has(s,"restaurant:") || catalog_has(s,"cafe:") ||
        catalog_has(s,"food & drink:")) return GR_FOOD;
    if (catalog_has(s,"shop:") || catalog_has(s,"public service:")) return GR_SHOPS;
    if (catalog_has(s,"location") || catalog_has(s,"address") ||
        catalog_has(s,"place:") || catalog_has(s,"country:") ||
        catalog_has(s,"closest mapped feature") ||
        catalog_has(section,"geographic")) return GR_PLACE;
    if (catalog_has(s,"official website") || catalog_has(s,"company website") ||
        catalog_has(s,"business website")) return GR_ORGWEB;
    if (catalog_has(s,"organization") || catalog_has(s,"company") ||
        catalog_has(s,"employer") || catalog_has(s,"subsidiary") ||
        catalog_has(s,"headquarters") || catalog_has(s,"operator:") ||
        catalog_has(s,"holder:") || catalog_has(section,"organization")) return GR_BUSINESS;
    if (catalog_has(s,"cve") || catalog_has(s,"vuln") ||
        catalog_has(s,"tls") || catalog_has(s,"ssl") ||
        catalog_has(s,"certificate")) return GR_SECURITY;
    if (catalog_has(s,"port") || catalog_has(s,"service") ||
        catalog_has(s,"banner") || catalog_has(s,"software")) return GR_SERVICES;
    if (catalog_has(s,"dns") || catalog_has(s,"domain") ||
        catalog_has(s,"hostname") || catalog_has(s,"subdomain")) return GR_DNS;
    if (catalog_has(s,"ip:") || catalog_has(s,"ipv4") ||
        catalog_has(s,"ipv6") || catalog_has(s,"asn") ||
        catalog_has(s,"prefix:") || catalog_has(section,"ip recon")) return GR_IP;
    if (catalog_has(s,"wallet") || catalog_has(s,"vin") ||
        catalog_has(s,"manufacturer") || catalog_has(section,"vehicle")) return GR_TECH;
    if (catalog_has(s,"occupation") || catalog_has(s,"education") ||
        catalog_has(s,"work history") || catalog_has(s,"profession")) return GR_WORK;
    if (catalog_has(s,"person:") || catalog_has(s,"born:") ||
        catalog_has(s,"name:") || catalog_has(section,"public name search")) return GR_IDENT;
    return GR_MISC;
}

/* Stable keys: prefer the actual profile/object URL over display names. */
static void catalog_make_key(char *out, size_t cap, const char *label) {
    const char *url = strcasestr(label,"https://");
    if (!url) url = strcasestr(label,"http://");
    const char *p = url ? url : label;
    size_t i = 0;
    while (*p && i + 1 < cap) {
        unsigned char ch = (unsigned char)*p;
        if (url && (isspace(ch) || ch == ')' || ch == ']' || ch == ',' || ch == ';')) break;
        if (!url && ch == '[') break;
        if (!url && isspace(ch)) {
            if (i > 0 && out[i-1] != ' ') out[i++] = ' ';
        } else out[i++] = (char)tolower(ch);
        p++;
    }
    while (i > 0 && (out[i-1] == ' ' || out[i-1] == '.' || out[i-1] == '/')) i--;
    out[i] = 0;
}
static void catalog_reset(void) {
    catalog_n = 0;
    catalog_section[0] = 0;
    catalog_last = -1;
    cat_sel = group_sel = item_sel = 0;
    cat_top = group_top = item_top = detail_top = 0;
}
static void catalog_ingest(const char *raw) {
    if (!raw || !raw[0]) return;
    char mark = raw[0];
    const char *label = raw[1] == ' ' ? raw + 2 : raw + 1;
    if (mark == '#') {
        snprintf(catalog_section,sizeof catalog_section,"%s",label);
        catalog_last = -1;
        return;
    }
    if (mark == 'i' && catalog_last >= 0) {
        CatalogItem *e = &catalog[catalog_last];
        if (catalog_has(label,"excerpt:")) {
            snprintf(e->excerpt,sizeof e->excerpt,"%s",label);
        } else if (catalog_has(label,"source:") || catalog_has(label,"http") ||
                   catalog_has(label,"based on")) {
            if (!e->source[0]) snprintf(e->source,sizeof e->source,"%s",label);
        }
        return;
    }
    if (!(mark == '+' || mark == '~' || mark == '=' || mark == '?' || mark == '!')) return;
    if (!*label || catalog_n >= CAT_MAX_ITEMS) return;
    CatalogItem item = {0};
    item.group = (unsigned char)catalog_group(label,catalog_section,mark);
    item.mark = mark;
    item.repeats = 1;
    snprintf(item.label,sizeof item.label,"%s",label);
    snprintf(item.section,sizeof item.section,"%s",catalog_section);
    catalog_make_key(item.key,sizeof item.key,label);
    /* Do not merge accounts that merely share the same display handle. */
    for (int i = 0; i < catalog_n; i++) {
        CatalogItem *old = &catalog[i];
        if (old->group == item.group && strcmp(old->key,item.key) == 0) {
            if (old->repeats < 65535) old->repeats++;
            catalog_last = i;
            return;
        }
    }
    catalog[catalog_n] = item;
    catalog_last = catalog_n++;
}
static int catalog_category_count(int cat) {
    int n = 0;
    for (int i=0;i<catalog_n;i++)
        if (group_cat[catalog[i].group] == cat) n++;
    return n;
}
static int catalog_group_count(int group) {
    int n = 0;
    for (int i=0;i<catalog_n;i++) if (catalog[i].group == group) n++;
    return n;
}
static int catalog_category_at(int visible) {
    for (int cat=0;cat<CAT_NUM;cat++)
        if (catalog_category_count(cat)>0 && visible-- == 0) return cat;
    return -1;
}
static int catalog_category_total(void) {
    int n=0;
    for (int c=0;c<CAT_NUM;c++) if (catalog_category_count(c)>0) n++;
    return n;
}
static int catalog_group_at(int cat,int visible) {
    for (int g=0;g<GR_NUM;g++)
        if (group_cat[g]==cat && catalog_group_count(g)>0 && visible-- == 0) return g;
    return -1;
}
static int catalog_group_total(int cat) {
    int n=0;
    for (int g=0;g<GR_NUM;g++)
        if (group_cat[g]==cat && catalog_group_count(g)>0) n++;
    return n;
}
static int catalog_item_at(int group,int visible) {
    for (int i=0;i<catalog_n;i++)
        if (catalog[i].group == group && visible-- == 0) return i;
    return -1;
}
static void catalog_limit(int *sel,int *top,int total) {
    if (total<=0) { *sel=0; *top=0; return; }
    if (*sel<0) *sel=0;
    if (*sel>=total) *sel=total-1;
    if (*sel<*top) *top=*sel;
    if (*sel>=*top+CAT_VISIBLE) *top=*sel-CAT_VISIBLE+1;
    if (*top<0) *top=0;
}
static void catalog_move(int d) {
    if (run_view == RV_OVERVIEW) {
        cat_sel += d;
        catalog_limit(&cat_sel,&cat_top,catalog_category_total());
    } else if (run_view == RV_GROUPS) {
        int cat=catalog_category_at(cat_sel);
        group_sel += d;
        catalog_limit(&group_sel,&group_top,cat<0?0:catalog_group_total(cat));
    } else if (run_view == RV_ITEMS) {
        int cat=catalog_category_at(cat_sel);
        int group=cat<0?-1:catalog_group_at(cat,group_sel);
        item_sel+=d;
        catalog_limit(&item_sel,&item_top,group<0?0:catalog_group_count(group));
    } else if (run_view == RV_DETAIL) {
        detail_top += d;
        if (detail_top<0) detail_top=0;
        if (detail_top>30) detail_top=30;
    }
}
static void catalog_open(void) {
    if (run_view == RV_OVERVIEW && catalog_category_total()>0) {
        run_view=RV_GROUPS;
        group_sel=group_top=0;
    } else if (run_view == RV_GROUPS) {
        int cat=catalog_category_at(cat_sel);
        if (cat>=0 && catalog_group_total(cat)>0) {
            run_view=RV_ITEMS;
            item_sel=item_top=0;
        }
    } else if (run_view == RV_ITEMS) {
        int cat=catalog_category_at(cat_sel);
        int group=cat<0?-1:catalog_group_at(cat,group_sel);
        if (group>=0 && catalog_group_count(group)>0) {
            run_view=RV_DETAIL;
            detail_top=0;
        }
    } else if (run_view == RV_DETAIL) run_view=RV_ITEMS;
}
static void catalog_back(void) {
    if (run_view==RV_DETAIL) run_view=RV_ITEMS;
    else if (run_view==RV_ITEMS) run_view=RV_GROUPS;
    else if (run_view==RV_GROUPS) run_view=RV_OVERVIEW;
    else if (run_view==RV_OVERVIEW) screen=S_MENU;
}
/* One shared button treatment for categories, subgroups and findings.
 * A real 1px outline distinguishes unselected buttons on white screens.
 * Selection is a solid black rounded shape with white text, never orange. */
static void catalog_row(int row,const char *label,int count,int chosen,char mark) {
    int y = 17 + row * CAT_ROW_H;
    int h = CAT_ROW_H - 1;
    const int x = 4, w = W - 13;
    button_card(x, y, w, h, chosen);
    Color fg = chosen ? C_LIGHT : C_INK;

    /* Compact mark preserves evidence status without relying on color. */
    if (mark == '!' || mark == '?') {
        text_px(9, y + 2, "!", fg);
    } else if (mark == '=' || mark == '+') {
        rect(10, y + 5, 3, 3, fg);
    } else {
        rect(10, y + 5, 2, 2, fg);
    }

    int maxChars = 30;
    if (count >= 0) {
        char number[12];
        snprintf(number, sizeof number, "%d", count);
        int bw = (int)strlen(number) * CW + 8;
        int bx = x + w - bw - 4;
        /* White counter chip remains legible on the selected black card. */
        pill(bx, y + 1, bw, 10, C_LIGHT);
        if (!chosen) rounded_border(bx, y + 1, bw, 10, C_INK);
        text_px(bx + 4, y + 2, number, C_INK);
        maxChars = (bx - 19 - 3) / CW;
    } else {
        text_px(x + w - 15, y + 2, ">", fg);
        maxChars = (x + w - 19 - 20) / CW;
    }
    if (maxChars < 1) maxChars = 1;
    if (maxChars > 34) maxChars = 34;
    char shown[36];
    snprintf(shown, sizeof shown, "%.*s", maxChars, label);
    text_px(18, y + 2, shown, fg);
}
static void catalog_draw_overview(void) {
    title("Categories");
    int n=catalog_category_total();
    if (!n) {
        text_px(10,26,"No matching findings yet.",C_INK);
        text_px(10,41,"Check network or tool status.",C_SOFT);
    }
    catalog_limit(&cat_sel,&cat_top,n);
    for (int r=0;r<CAT_VISIBLE;r++) {
        int cat=catalog_category_at(cat_top+r);
        if (cat<0) break;
        catalog_row(r,cat_titles[cat],catalog_category_count(cat),cat_top+r==cat_sel,0);
    }
    softkeys("Home","Back",NULL,"Open");
}
static void catalog_draw_groups(void) {
    int cat=catalog_category_at(cat_sel);
    if (cat<0) {catalog_draw_overview();return;}
    title(cat_titles[cat]);
    int n=catalog_group_total(cat);
    catalog_limit(&group_sel,&group_top,n);
    for (int r=0;r<CAT_VISIBLE;r++) {
        int g=catalog_group_at(cat,group_top+r);
        if (g<0) break;
        catalog_row(r,group_titles[g],catalog_group_count(g),group_top+r==group_sel,0);
    }
    softkeys("Home","Back",NULL,"Open");
}
static void catalog_draw_items(void) {
    int cat=catalog_category_at(cat_sel);
    int group=cat<0?-1:catalog_group_at(cat,group_sel);
    if (group<0) {catalog_draw_groups();return;}
    title(group_titles[group]);
    int n=catalog_group_count(group);
    catalog_limit(&item_sel,&item_top,n);
    for (int r=0;r<CAT_VISIBLE;r++) {
        int i=catalog_item_at(group,item_top+r);
        if (i<0) break;
        catalog_row(r,catalog[i].label,-1,item_top+r==item_sel,catalog[i].mark);
    }
    softkeys("Home","Back",NULL,"View");
}
static int catalog_wrap_text(const char *p,char dst[][COLS+1],int maxRows) {
    int line=0;
    while (*p && line<maxRows) {
        while (*p==' ') p++;
        if (*p=='\n') {dst[line++][0]=0;p++;continue;}
        int len=(int)strcspn(p,"\n");
        int n=len > COLS-4 ? COLS-4 : len;
        int br=n;
        if (len>n) for (int i=n;i>7;i--) if (p[i]==' ') {br=i;break;}
        memcpy(dst[line],p,(size_t)br);
        dst[line][br]=0;
        line++;
        p+=br;
        while (*p==' ') p++;
        if (*p=='\n') p++;
    }
    return line;
}
static void catalog_draw_detail(void) {
    int cat=catalog_category_at(cat_sel);
    int group=cat<0?-1:catalog_group_at(cat,group_sel);
    int id=group<0?-1:catalog_item_at(group,item_sel);
    if (id<0){catalog_draw_items();return;}
    const CatalogItem *e=&catalog[id];
    title("Finding details");
    char combined[1000];
    snprintf(combined,sizeof combined,"%s\n\nCategory: %s\nGroup: %s\nStatus: %s\nFound in: %s\n%s%s\n%s%s%s",
        e->label,cat_titles[group_cat[e->group]],group_titles[e->group],
        e->mark=='='?"Reviewed":e->mark=='!'?"Warning":e->mark=='?'?"Unverified":"Source indication",
        e->section[0]?e->section:"Search output",
        e->excerpt[0]?"\n":"",e->excerpt,
        e->source[0]?"Source / context:\n":"",
        e->source[0]?e->source:"",
        e->repeats>1?"\nRepeated results were merged.":"");
    char wrapped[64][COLS+1]={{0}};
    int n=catalog_wrap_text(combined,wrapped,64);
    if (detail_top>n-CAT_VISIBLE) detail_top=n>CAT_VISIBLE?n-CAT_VISIBLE:0;
    for (int r=0;r<CAT_VISIBLE && detail_top+r<n;r++)
        text_px(9,19+r*CAT_ROW_H,wrapped[detail_top+r],r==0?C_INK:C_SOFT);
    softkeys("Home","Back",NULL,"Back");
}
static void catalog_draw(void) {
    if (run_view==RV_OVERVIEW) catalog_draw_overview();
    else if (run_view==RV_GROUPS) catalog_draw_groups();
    else if (run_view==RV_ITEMS) catalog_draw_items();
    else if (run_view==RV_DETAIL) catalog_draw_detail();
}
static void catalog_click_row(int row) {
    if (row<0 || row>=CAT_VISIBLE) return;
    if (run_view==RV_OVERVIEW) {
        if (catalog_category_at(cat_top+row)<0) return;
        cat_sel=cat_top+row;
    } else if (run_view==RV_GROUPS) {
        int cat=catalog_category_at(cat_sel);
        if (cat<0 || catalog_group_at(cat,group_top+row)<0) return;
        group_sel=group_top+row;
    } else if (run_view==RV_ITEMS) {
        int cat=catalog_category_at(cat_sel);
        int group=cat<0?-1:catalog_group_at(cat,group_sel);
        if (group<0 || catalog_item_at(group,item_top+row)<0) return;
        item_sel=item_top+row;
    } else return;
    catalog_open();
}
#endif
