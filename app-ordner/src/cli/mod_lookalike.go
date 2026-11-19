package main

import (
	"context"
	"sort"
	"strings"
	"sync"
	"time"
)

// Lookalike / typosquatting detection in the spirit of dnstwist: generate
// typo, homoglyph, bitsquat and TLD variants of a domain, then check which
// are registered, have mail servers or serve a website. Brand protection
// without a commercial feed.

var qwertyAdj = map[rune]string{
	'q': "wa", 'w': "qes", 'e': "wrd", 'r': "etf", 't': "ryg", 'y': "tuh", 'u': "yij", 'i': "uok", 'o': "ipl", 'p': "ol",
	'a': "qsz", 's': "awdz", 'd': "sefx", 'f': "drgc", 'g': "fthv", 'h': "gyjb", 'j': "hukn", 'k': "jilm", 'l': "kop",
	'z': "asx", 'x': "zsdc", 'c': "xdfv", 'v': "cfgb", 'b': "vghn", 'n': "bhjm", 'm': "njk",
	'1': "2q", '2': "13w", '3': "24e", '4': "35r", '5': "46t", '6': "57y", '7': "68u", '8': "79i", '9': "80o", '0': "9p",
}

// ASCII look-alikes (multi-char too) and Unicode homoglyphs (IDN).
var asciiGlyphs = map[string][]string{
	"m": {"rn", "nn"}, "rn": {"m"}, "w": {"vv"}, "vv": {"w"}, "d": {"cl"}, "cl": {"d"},
	"l": {"1", "i"}, "i": {"1", "l"}, "o": {"0"}, "0": {"o"}, "1": {"l"}, "g": {"q"}, "q": {"g"},
}

var idnGlyphs = map[rune][]rune{
	'a': {'а', 'à', 'á', 'ä', 'å'}, 'c': {'с', 'ç'}, 'e': {'е', 'é', 'è', 'ë'}, 'i': {'і', 'í', 'ï'},
	'o': {'о', 'ó', 'ö', 'ø'}, 'p': {'р'}, 's': {'ѕ'}, 'x': {'х'}, 'y': {'у', 'ý'}, 'u': {'ü', 'ú'},
	'n': {'ñ'}, 'k': {'κ'}, 'h': {'һ'}, 'j': {'ј'},
}

var altTLDs = []string{"com", "net", "org", "de", "eu", "info", "biz", "co", "io", "app", "online", "shop", "store", "site", "xyz", "top", "at", "ch", "us", "uk", "co.uk"}

// lookalikes returns candidate domains (ASCII/punycode) with their technique.
func lookalikes(domain string) map[string]string {
	reg := registrableDomain(domain)
	if reg == "" {
		reg = domain
	}
	suf := publicSuffix(reg)
	name := strings.TrimSuffix(reg, "."+suf)
	out := map[string]string{}
	add := func(n, s, tech string) {
		n = strings.Trim(n, "-")
		if n == "" || strings.Contains(n, "--") && !strings.HasPrefix(n, "xn--") || len(n) > 63 {
			return
		}
		d := n + "." + s
		if d == reg {
			return
		}
		if _, ok := out[d]; !ok {
			out[d] = tech
		}
	}
	rs := []rune(name)
	for i := range rs {
		add(string(rs[:i])+string(rs[i+1:]), suf, "omission")
		add(string(rs[:i+1])+string(rs[i:]), suf, "repetition")
		if i+1 < len(rs) {
			t := append([]rune(nil), rs...)
			t[i], t[i+1] = t[i+1], t[i]
			add(string(t), suf, "transposition")
		}
		for _, c := range qwertyAdj[rs[i]] {
			add(string(rs[:i])+string(c)+string(rs[i+1:]), suf, "replacement")
			add(string(rs[:i])+string(c)+string(rs[i:]), suf, "insertion")
		}
		if i > 0 {
			add(string(rs[:i])+"-"+string(rs[i:]), suf, "hyphenation")
			add(string(rs[:i])+"."+string(rs[i:]), suf, "subdomain")
		}
		if strings.ContainsRune("aeiou", rs[i]) {
			for _, v := range "aeiou" {
				if v != rs[i] {
					add(string(rs[:i])+string(v)+string(rs[i+1:]), suf, "vowel-swap")
				}
			}
		}
		// bitsquatting: one flipped bit that still gives a valid DNS char
		if rs[i] < 128 {
			for b := 0; b < 8; b++ {
				c := rune(byte(rs[i]) ^ (1 << b))
				if (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-' {
					add(string(rs[:i])+string(c)+string(rs[i+1:]), suf, "bitsquatting")
				}
			}
		}
		for _, g := range idnGlyphs[rs[i]] {
			if p, ok := punyLabel(string(rs[:i]) + string(g) + string(rs[i+1:])); ok {
				add(p, suf, "homoglyph-idn")
			}
		}
	}
	for from, tos := range asciiGlyphs {
		for idx := strings.Index(name, from); idx >= 0; {
			for _, to := range tos {
				add(name[:idx]+to+name[idx+len(from):], suf, "homoglyph")
			}
			next := strings.Index(name[idx+1:], from)
			if next < 0 {
				break
			}
			idx += next + 1
		}
	}
	for _, t := range altTLDs {
		if t != suf {
			add(name, t, "tld-swap")
		}
	}
	add(name+"-login", suf, "addition")
	add(name+"-secure", suf, "addition")
	add(name+"-online", suf, "addition")
	add("my"+name, suf, "addition")
	add(name+"s", suf, "addition")
	return out
}

// punyLabel encodes one label to its ACE form (RFC 3492). ok=false on
// overflow; ASCII-only labels are returned unchanged.
func punyLabel(label string) (string, bool) {
	const (
		base, tmin, tmax, skew, damp = 36, 1, 26, 38, 700
		initialBias, initialN        = 72, 128
	)
	rs := []rune(label)
	var out []byte
	for _, r := range rs {
		if r < 128 {
			out = append(out, byte(r))
		}
	}
	b := len(out)
	if b == len(rs) {
		return label, true
	}
	if b > 0 {
		out = append(out, '-')
	}
	digit := func(d int) byte {
		if d < 26 {
			return byte('a' + d)
		}
		return byte('0' + d - 26)
	}
	adapt := func(delta, numPoints int, first bool) int {
		if first {
			delta /= damp
		} else {
			delta /= 2
		}
		delta += delta / numPoints
		k := 0
		for delta > ((base-tmin)*tmax)/2 {
			delta /= base - tmin
			k += base
		}
		return k + (base-tmin+1)*delta/(delta+skew)
	}
	n, delta, bias, h := initialN, 0, initialBias, b
	for h < len(rs) {
		m := int(^uint(0) >> 1)
		for _, r := range rs {
			if int(r) >= n && int(r) < m {
				m = int(r)
			}
		}
		delta += (m - n) * (h + 1)
		n = m
		for _, r := range rs {
			if int(r) < n {
				delta++
			}
			if int(r) == n {
				q := delta
				for k := base; ; k += base {
					t := k - bias
					if t < tmin {
						t = tmin
					} else if t > tmax {
						t = tmax
					}
					if q < t {
						break
					}
					out = append(out, digit(t+(q-t)%(base-t)))
					q = (q - t) / (base - t)
				}
				out = append(out, digit(q))
				bias = adapt(delta, h+1, h == b)
				delta = 0
				h++
			}
		}
		delta++
		n++
	}
	return "xn--" + string(out), true
}

// maxLookalikeChecks bounds DNS traffic per domain on the handheld.
var maxLookalikeChecks = 400

var modLookalike = &Module{
	Name: "lookalike", Desc: "Typosquatting / homoglyph domains (dnstwist style)",
	In: []Kind{KDomain}, Out: []Kind{KLookalike, KIssue}, Timeout: 120 * time.Second,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		if in.Depth > 0 && registrableDomain(in.Value) != in.Value {
			return nil
		}
		cands := lookalikes(in.Value)
		names := make([]string, 0, len(cands))
		for d := range cands {
			names = append(names, d)
		}
		sort.Strings(names)
		if len(names) > maxLookalikeChecks {
			names = names[:maxLookalikeChecks]
		}
		sem := make(chan struct{}, 16)
		var wg sync.WaitGroup
		for _, d := range names {
			wg.Add(1)
			go func(d string) {
				defer wg.Done()
				sem <- struct{}{}
				defer func() { <-sem }()
				checkLookalike(ctx, d, cands[d], in.Value, out)
			}(d)
		}
		wg.Wait()
		return ctx.Err()
	},
}

func checkLookalike(ctx context.Context, d, tech, orig string, out *Out) {
	ns, err := dohLookup(ctx, d, "NS")
	if err != nil || ns.NX {
		return
	}
	a := dohValues(ctx, d, "A")
	mx := dohValues(ctx, d, "MX")
	if len(ns.Answers) == 0 && len(a) == 0 {
		return // exists only as an empty node, e.g. part of the suffix
	}
	data := map[string]string{"technique": tech, "of": orig}
	sev, what := SevLow, "registered"
	if len(a) > 0 {
		sev, what = SevMedium, "registered, has website IP "+a[0]
		data["a"] = strings.Join(a, " ")
	}
	if len(mx) > 0 {
		sev, what = SevHigh, what+", has MAIL server (phishing-capable)"
		data["mx"] = strings.Join(mx, " ")
	}
	if tech == "tld-swap" && sev < SevHigh {
		sev = SevLow // other TLDs are often owned defensively
	}
	out.Add(Finding{Type: KLookalike, Value: d, Source: "dns", Confidence: 90, Severity: sev,
		Detail: tech + ": " + what, Data: data})
}
