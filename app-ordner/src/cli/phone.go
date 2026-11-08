package main

import (
	"regexp"
	"strings"
)

var callingCodes = map[string]string{
	"1": "USA / Canada (NANP)", "7": "Russia / Kazakhstan", "20": "Egypt", "27": "South Africa",
	"30": "Greece", "31": "Netherlands", "32": "Belgium", "33": "France", "34": "Spain",
	"36": "Hungary", "39": "Italy", "40": "Romania", "41": "Switzerland", "43": "Austria",
	"44": "United Kingdom", "45": "Denmark", "46": "Sweden", "47": "Norway", "48": "Poland",
	"49": "Germany", "51": "Peru", "52": "Mexico", "53": "Cuba", "54": "Argentina",
	"55": "Brazil", "56": "Chile", "57": "Colombia", "58": "Venezuela", "60": "Malaysia",
	"61": "Australia", "62": "Indonesia", "63": "Philippines", "64": "New Zealand", "65": "Singapore",
	"66": "Thailand", "81": "Japan", "82": "South Korea", "84": "Vietnam", "86": "China",
	"90": "Turkey", "91": "India", "92": "Pakistan", "93": "Afghanistan", "94": "Sri Lanka",
	"95": "Myanmar", "98": "Iran", "212": "Morocco", "213": "Algeria", "216": "Tunisia",
	"218": "Libya", "234": "Nigeria", "254": "Kenya", "255": "Tanzania", "351": "Portugal",
	"352": "Luxembourg", "353": "Ireland", "354": "Iceland", "355": "Albania", "356": "Malta",
	"357": "Cyprus", "358": "Finland", "359": "Bulgaria", "370": "Lithuania", "371": "Latvia",
	"372": "Estonia", "373": "Moldova", "374": "Armenia", "375": "Belarus", "376": "Andorra",
	"377": "Monaco", "378": "San Marino", "380": "Ukraine", "381": "Serbia", "382": "Montenegro",
	"385": "Croatia", "386": "Slovenia", "387": "Bosnia and Herzegovina", "389": "North Macedonia",
	"420": "Czechia", "421": "Slovakia", "423": "Liechtenstein", "852": "Hong Kong", "853": "Macao",
	"880": "Bangladesh", "886": "Taiwan", "961": "Lebanon", "962": "Jordan", "964": "Iraq",
	"966": "Saudi Arabia", "971": "United Arab Emirates", "972": "Israel", "974": "Qatar",
	"977": "Nepal", "995": "Georgia", "998": "Uzbekistan",
}

// Expected length of the national number (without country code and leading 0): min, max.
var nationalLen = map[string][2]int{
	"49": {5, 13}, "43": {4, 13}, "41": {9, 9}, "1": {10, 10}, "44": {9, 10}, "33": {9, 9},
	"39": {6, 12}, "34": {9, 9}, "31": {9, 9}, "48": {9, 9}, "32": {8, 9}, "45": {8, 8},
	"46": {7, 13}, "47": {8, 8}, "420": {9, 9}, "352": {4, 11},
}

var nonDigits = regexp.MustCompile(`[^0-9]`)

func runPhone(raw string) {
	head("Phone number: %s", raw)
	s := strings.TrimSpace(raw)
	assumed := false
	plus := strings.HasPrefix(s, "+")
	digits := nonDigits.ReplaceAllString(s, "")
	switch {
	case plus:
		// already international
	case strings.HasPrefix(digits, "00"):
		digits = digits[2:]
	case strings.HasPrefix(digits, "0"):
		digits = "49" + digits[1:]
		assumed = true
	default:
		warn("Please enter with country code (+49 ...) or start with 0")
		return
	}
	if len(digits) < 7 || len(digits) > 15 {
		warn("Invalid length: %d digits (E.164: 7-15)", len(digits))
		return
	}
	if assumed {
		info("Assumption: German number (starts with 0)")
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
		warn("Unknown country code")
		found("E.164: +%s", digits)
		return
	}
	ns := digits[len(cc):]
	found("E.164: +%s", digits)
	found("International: +%s %s", cc, groupDigits(ns))
	found("Country: %s (+%s)", country, cc)

	if l, ok := nationalLen[cc]; ok {
		if len(ns) >= l[0] && len(ns) <= l[1] {
			found("Length plausible: %d national digits", len(ns))
		} else {
			warn("Unusual length: %d national digits (expected %d-%d)", len(ns), l[0], l[1])
		}
	}
	info("Type: %s", lineType(cc, ns))
	info("Carrier/owner cannot be determined (number portability); no owner lookup")
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
			return "Mobile"
		case has("800"):
			return "Toll-free (0800)"
		case has("900"):
			return "Premium service (0900)"
		case has("180"):
			return "Service number (0180)"
		case has("700"):
			return "Personal number (0700)"
		case has("32"):
			return "National subscriber number (032)"
		case has("19"):
			return "Online services (019)"
		case has("2", "3", "4", "5", "6", "7", "8", "9"):
			return "Landline (local area)"
		}
	case "43":
		switch {
		case has("6"):
			return "Mobile"
		case has("800"):
			return "Toll-free"
		case has("900", "901", "930", "931"):
			return "Premium service"
		default:
			return "Landline"
		}
	case "41":
		switch {
		case has("74", "75", "76", "77", "78", "79"):
			return "Mobile"
		case has("800"):
			return "Toll-free"
		case has("900", "901", "906"):
			return "Premium service"
		default:
			return "Landline"
		}
	case "44":
		switch {
		case has("70"):
			return "Personal number"
		case has("7"):
			return "Mobile"
		case has("800", "808"):
			return "Toll-free"
		case has("9"):
			return "Premium service"
		case has("1", "2"):
			return "Landline (geographic)"
		case has("3"):
			return "Non-geographic"
		}
	case "1":
		switch {
		case has("800", "833", "844", "855", "866", "877", "888"):
			return "Toll-free"
		case has("900"):
			return "Premium service"
		default:
			return "Landline or mobile (NANP does not distinguish)"
		}
	}
	return "Unknown (only country code evaluated)"
}
