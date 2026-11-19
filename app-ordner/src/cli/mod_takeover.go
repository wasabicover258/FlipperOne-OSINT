package main

import (
	"context"
	_ "embed"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// Subdomain takeover check: a host whose CNAME points to a cloud service
// where the resource no longer exists can be claimed by anyone. Patterns
// follow the community list "can-i-take-over-xyz"; the built-in copy can be
// replaced by data/takeover.json in the data dir (offline data pack).

//go:embed data/takeover.json
var takeoverBuiltin []byte

type takeoverSig struct {
	Service     string   `json:"service"`
	CNAME       []string `json:"cname"`
	Fingerprint string   `json:"fingerprint"`
	NXDomain    bool     `json:"nxdomain"`
}

var (
	takeoverOnce sync.Once
	takeoverSigs []takeoverSig
)

func loadTakeoverSigs() []takeoverSig {
	takeoverOnce.Do(func() {
		src := takeoverBuiltin
		if b, err := os.ReadFile(filepath.Join(dataDir(), "data", "takeover.json")); err == nil {
			src = b
		}
		if json.Unmarshal(src, &takeoverSigs) != nil {
			json.Unmarshal(takeoverBuiltin, &takeoverSigs)
		}
	})
	return takeoverSigs
}

func matchTakeover(cname string) *takeoverSig {
	cname = strings.ToLower(strings.TrimSuffix(cname, "."))
	for i, s := range loadTakeoverSigs() {
		for _, p := range s.CNAME {
			if cname == p || strings.HasSuffix(cname, "."+p) || strings.Contains(cname, p) {
				return &loadTakeoverSigs()[i]
			}
		}
	}
	return nil
}

// takeoverVerdict decides from the observed state. body may be nil if the
// HTTP request failed.
func takeoverVerdict(sig *takeoverSig, targetNX bool, body []byte) (Severity, string) {
	if sig == nil {
		if targetNX {
			return SevMedium, "dangling CNAME: target does not exist (unknown service, check manually)"
		}
		return SevInfo, ""
	}
	if sig.NXDomain && targetNX {
		return SevCritical, sig.Service + " resource is unclaimed (NXDOMAIN) - takeover likely"
	}
	if sig.Fingerprint != "" && body != nil && strings.Contains(string(body), sig.Fingerprint) {
		return SevCritical, sig.Service + " answers with its 'not found' page - takeover likely"
	}
	if targetNX {
		return SevHigh, sig.Service + " CNAME target does not resolve - takeover possible"
	}
	return SevInfo, ""
}

var modTakeover = &Module{
	Name: "takeover", Desc: "Subdomain takeover (dangling CNAME to cloud services)",
	In: []Kind{KHost}, Out: []Kind{KIssue}, Timeout: 25 * time.Second, Retries: 1,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		r, err := dohLookup(ctx, in.Value, "CNAME")
		if err != nil {
			return err
		}
		if len(r.Answers) == 0 {
			return nil
		}
		target := r.Answers[len(r.Answers)-1].Data
		sig := matchTakeover(target)
		tr, err := dohLookup(ctx, target, "A")
		if err != nil {
			return err
		}
		var body []byte
		if sig != nil && sig.Fingerprint != "" && !tr.NX {
			for _, scheme := range []string{"https://", "http://"} {
				if code, b, err := fetch(ctx, scheme+in.Value+"/", nil); err == nil && code > 0 {
					body = b
					break
				}
			}
		}
		sev, why := takeoverVerdict(sig, tr.NX, body)
		if why == "" {
			return nil
		}
		svc := "unknown"
		if sig != nil {
			svc = sig.Service
		}
		out.Add(Finding{Type: KIssue, Value: "Subdomain takeover: " + in.Value, Severity: sev, Confidence: 85,
			Detail: in.Value + " -> " + target + ": " + why,
			Data:   map[string]string{"check": "takeover", "cname": target, "service": svc, "host": in.Value}})
		return nil
	},
}
