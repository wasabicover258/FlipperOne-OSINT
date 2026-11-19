package main

import (
	_ "embed"
	"os"
	"path/filepath"
	"strings"
	"sync"
)

// Public Suffix List. A compact built-in list covers the common multi-label
// suffixes (co.uk, com.au ...); "osint-cli update-data" downloads the full
// list into the data dir, which is then preferred (offline data pack).

//go:embed data/psl_min.txt
var pslMin string

var (
	pslOnce sync.Once
	pslSet  map[string]bool
)

func loadPSL() {
	pslSet = map[string]bool{}
	src := pslMin
	if b, err := os.ReadFile(filepath.Join(dataDir(), "data", "public_suffix_list.dat")); err == nil {
		src = string(b)
	}
	for _, l := range strings.Split(src, "\n") {
		l = strings.TrimSpace(l)
		if l == "" || strings.HasPrefix(l, "//") || strings.HasPrefix(l, "!") {
			continue
		}
		pslSet[strings.TrimPrefix(l, "*.")] = true
	}
}

// publicSuffix returns the longest known public suffix of host (at least
// the last label).
func publicSuffix(host string) string {
	pslOnce.Do(loadPSL)
	labels := strings.Split(host, ".")
	for i := 0; i < len(labels); i++ {
		if s := strings.Join(labels[i:], "."); pslSet[s] {
			return s
		}
	}
	return labels[len(labels)-1]
}

// registrableDomain returns eTLD+1 of a host ("" if host is a suffix).
func registrableDomain(host string) string {
	host = strings.ToLower(strings.Trim(host, "."))
	if host == "" {
		return ""
	}
	suf := publicSuffix(host)
	if host == suf {
		return ""
	}
	rest := strings.TrimSuffix(host, "."+suf)
	if i := strings.LastIndexByte(rest, '.'); i >= 0 {
		rest = rest[i+1:]
	}
	return rest + "." + suf
}
