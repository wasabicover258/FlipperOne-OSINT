package main

import (
	"regexp"
	"strings"
)

var callingCodes = map[string]string{
	"1": "USA / KANADA (NANP)", "7": "RUSSLAND / KASACHSTAN", "20": "AEGYPTEN", "27": "SUEDAFRIKA",
	"30": "GRIECHENLAND", "31": "NIEDERLANDE", "32": "BELGIEN", "33": "FRANKREICH", "34": "SPANIEN",
	"36": "UNGARN", "39": "ITALIEN", "40": "RUMAENIEN", "41": "SCHWEIZ", "43": "OESTERREICH",
	"44": "GROSSBRITANNIEN", "45": "DAENEMARK", "46": "SCHWEDEN", "47": "NORWEGEN", "48": "POLEN",
	"49": "DEUTSCHLAND", "51": "PERU", "52": "MEXIKO", "53": "KUBA", "54": "ARGENTINIEN",
	"55": "BRASILIEN", "56": "CHILE", "57": "KOLUMBIEN", "58": "VENEZUELA", "60": "MALAYSIA",
	"61": "AUSTRALIEN", "62": "INDONESIEN", "63": "PHILIPPINEN", "64": "NEUSEELAND", "65": "SINGAPUR",
	"66": "THAILAND", "81": "JAPAN", "82": "SUEDKOREA", "84": "VIETNAM", "86": "CHINA",
	"90": "TUERKEI", "91": "INDIEN", "92": "PAKISTAN", "93": "AFGHANISTAN", "94": "SRI LANKA",
	"95": "MYANMAR", "98": "IRAN", "212": "MAROKKO", "213": "ALGERIEN", "216": "TUNESIEN",
	"218": "LIBYEN", "234": "NIGERIA", "254": "KENIA", "255": "TANSANIA", "351": "PORTUGAL",
	"352": "LUXEMBURG", "353": "IRLAND", "354": "ISLAND", "355": "ALBANIEN", "356": "MALTA",
	"357": "ZYPERN", "358": "FINNLAND", "359": "BULGARIEN", "370": "LITAUEN", "371": "LETTLAND",
	"372": "ESTLAND", "373": "MOLDAWIEN", "374": "ARMENIEN", "375": "WEISSRUSSLAND", "376": "ANDORRA",
	"377": "MONACO", "378": "SAN MARINO", "380": "UKRAINE", "381": "SERBIEN", "382": "MONTENEGRO",
	"385": "KROATIEN", "386": "SLOWENIEN", "387": "BOSNIEN-HERZEGOWINA", "389": "NORDMAZEDONIEN",
	"420": "TSCHECHIEN", "421": "SLOWAKEI", "423": "LIECHTENSTEIN", "852": "HONGKONG", "853": "MACAO",
	"880": "BANGLADESCH", "886": "TAIWAN", "961": "LIBANON", "962": "JORDANIEN", "964": "IRAK",
	"966": "SAUDI-ARABIEN", "971": "VER. ARAB. EMIRATE", "972": "ISRAEL", "974": "KATAR",
	"977": "NEPAL", "995": "GEORGIEN", "998": "USBEKISTAN",
}

// Erwartete Laenge der nationalen Nummer (ohne Landesvorwahl und fuehrende 0): min, max.
var nationalLen = map[string][2]int{
	"49": {5, 13}, "43": {4, 13}, "41": {9, 9}, "1": {10, 10}, "44": {9, 10}, "33": {9, 9},
	"39": {6, 12}, "34": {9, 9}, "31": {9, 9}, "48": {9, 9}, "32": {8, 9}, "45": {8, 8},
	"46": {7, 13}, "47": {8, 8}, "420": {9, 9}, "352": {4, 11},
}

var nonDigits = regexp.MustCompile(`[^0-9]`)

func runPhone(raw string) {
	head("TELEFONNUMMER: %s", raw)
	s := strings.TrimSpace(raw)
	assumed := false
	plus := strings.HasPrefix(s, "+")
	digits := nonDigits.ReplaceAllString(s, "")
	switch {
	case plus:
		// bereits international
	case strings.HasPrefix(digits, "00"):
		digits = digits[2:]
	case strings.HasPrefix(digits, "0"):
		digits = "49" + digits[1:]
		assumed = true
	default:
		warn("BITTE MIT LAENDERVORWAHL ANGEBEN (+49 ...) ODER MIT 0 BEGINNEN")
		return
	}
	if len(digits) < 7 || len(digits) > 15 {
		warn("UNGUELTIGE LAENGE: %d ZIFFERN (E.164: 7-15)", len(digits))
		return
	}
	if assumed {
		info("ANNAHME: DEUTSCHE NUMMER (BEGINN MIT 0)")
	}

	cc, country := "", ""
	for _, n := range []int{3, 2, 1} {
		if len(digits) > n {
			if name, ok := callingCodes[digits[:n]]; ok {
				cc, country = digits[:n], name
				break
			}
		}
	}
	if cc == "" {
		warn("LAENDERVORWAHL UNBEKANNT")
		found("E.164: +%s", digits)
		return
	}
	ns := digits[len(cc):]
	found("E.164: +%s", digits)
	found("INTERNATIONAL: +%s %s", cc, groupDigits(ns))
	found("LAND: %s (+%s)", country, cc)

	if l, ok := nationalLen[cc]; ok {
		if len(ns) >= l[0] && len(ns) <= l[1] {
			found("LAENGE PLAUSIBEL: %d ZIFFERN NATIONAL", len(ns))
		} else {
			warn("LAENGE UNUEBLICH: %d ZIFFERN NATIONAL (ERWARTET %d-%d)", len(ns), l[0], l[1])
		}
	}
	info("TYP: %s", lineType(cc, ns))
	info("NETZ/HALTER NICHT BESTIMMBAR (RUFNUMMERNMITNAHME), KEINE HALTERABFRAGE")
}

func groupDigits(s string) string {
	if len(s) <= 4 {
		return s
	}
	return s[:3] + " " + s[3:]
}

func lineType(cc, ns string) string {
	has := func(p ...string) bool {
		for _, x := range p {
			if strings.HasPrefix(ns, x) {
				return true
			}
		}
		return false
	}
	switch cc {
	case "49":
		switch {
		case has("15", "16", "17"):
			return "MOBILFUNK"
		case has("800"):
			return "FREECALL (0800)"
		case has("900"):
			return "PREMIUM-DIENST (0900)"
		case has("180"):
			return "SERVICE-NUMMER (0180)"
		case has("700"):
			return "PERSOENLICHE RUFNUMMER (0700)"
		case has("32"):
			return "NATIONALE TEILNEHMERRUFNUMMER (032)"
		case has("19"):
			return "ONLINE-DIENSTE (019)"
		case has("2", "3", "4", "5", "6", "7", "8", "9"):
			return "FESTNETZ (ORTSNETZ)"
		}
	case "43":
		switch {
		case has("6"):
			return "MOBILFUNK"
		case has("800"):
			return "FREECALL"
		case has("900", "901", "930", "931"):
			return "PREMIUM-DIENST"
		default:
			return "FESTNETZ"
		}
	case "41":
		switch {
		case has("74", "75", "76", "77", "78", "79"):
			return "MOBILFUNK"
		case has("800"):
			return "FREECALL"
		case has("900", "901", "906"):
			return "PREMIUM-DIENST"
		default:
			return "FESTNETZ"
		}
	case "44":
		switch {
		case has("70"):
			return "PERSOENLICHE RUFNUMMER"
		case has("7"):
			return "MOBILFUNK"
		case has("800", "808"):
			return "FREECALL"
		case has("9"):
			return "PREMIUM-DIENST"
		case has("1", "2"):
			return "FESTNETZ (GEOGRAFISCH)"
		case has("3"):
			return "NICHT-GEOGRAFISCH"
		}
	case "1":
		switch {
		case has("800", "833", "844", "855", "866", "877", "888"):
			return "FREECALL (TOLL-FREE)"
		case has("900"):
			return "PREMIUM-DIENST"
		default:
			return "FESTNETZ ODER MOBIL (NANP UNTERSCHEIDET NICHT)"
		}
	}
	return "UNBEKANNT (NUR LAENDERVORWAHL AUSGEWERTET)"
}
