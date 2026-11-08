package main

import (
	"sort"
	"strings"
)

var translit = strings.NewReplacer(
	"ä", "ae", "ö", "oe", "ü", "ue", "ß", "ss",
	"é", "e", "è", "e", "ê", "e", "á", "a", "à", "a", "â", "a", "í", "i", "ì", "i", "î", "i",
	"ó", "o", "ò", "o", "ô", "o", "ú", "u", "ù", "u", "û", "u", "ç", "c", "ñ", "n", "å", "a",
	"ø", "o", "æ", "ae", "ï", "i", "ë", "e", "ÿ", "y", "ł", "l", "š", "s", "ž", "z", "č", "c",
)

func cleanPart(s string) string {
	s = translit.Replace(strings.ToLower(strings.TrimSpace(s)))
	var b strings.Builder
	for _, r := range s {
		if (r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') {
			b.WriteRune(r)
		}
	}
	return b.String()
}

// runName erzeugt typische Username-Varianten aus Vor- und Nachname (rein lokal).
func runName(raw string) {
	head("NAME -> USERNAME-VARIANTEN")
	parts := strings.Fields(raw)
	if len(parts) < 2 {
		warn("BITTE VOR- UND NACHNAME ANGEBEN")
		return
	}
	first := cleanPart(parts[0])
	last := cleanPart(parts[len(parts)-1])
	if first == "" || last == "" {
		warn("NAME ENTHAELT KEINE VERWENDBAREN ZEICHEN")
		return
	}
	f := first[:1]
	l := last[:1]
	set := map[string]bool{}
	add := func(v string) {
		if len(v) >= 3 {
			set[v] = true
		}
	}
	for _, sep := range []string{"", ".", "_", "-"} {
		add(first + sep + last)
		add(last + sep + first)
		add(f + sep + last)
		add(first + sep + l)
		add(last + sep + f)
	}
	add(first)
	add(last)
	add(first + last[:min(3, len(last))])
	list := make([]string, 0, len(set))
	for k := range set {
		list = append(list, k)
	}
	sort.Strings(list)
	found("%d VARIANTEN ERZEUGT (OHNE ZAHLEN)", len(list))
	line := ""
	for _, v := range list {
		if len(line)+len(v)+2 > 38 && line != "" {
			info("%s", line)
			line = ""
		}
		if line != "" {
			line += ", "
		}
		line += v
	}
	if line != "" {
		info("%s", line)
	}
	info("TIPP: EINE VARIANTE ALS USERNAME PRUEFEN")
	info("KEINE PERSONENSUCHE, NUR TEXT-VARIANTEN")
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
