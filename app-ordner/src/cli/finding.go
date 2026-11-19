package main

import (
	"strings"
	"time"
)

// Kind is the entity type of a finding. Modules declare which kinds they
// consume and which they produce; the engine routes findings accordingly.
type Kind string

const (
	KDomain    Kind = "domain"    // registrable domain, the usual seed
	KHost      Kind = "hostname"  // any FQDN inside scope (subdomain, MX, NS ...)
	KIP        Kind = "ip"        // IPv4 or IPv6 address
	KASN       Kind = "asn"       // e.g. AS15169
	KNetblock  Kind = "netblock"  // CIDR prefix
	KCert      Kind = "cert"      // TLS certificate (value = subject CN + serial)
	KPort      Kind = "port"      // value = ip:port/proto
	KCPE       Kind = "cpe"       // software identifier
	KCVE       Kind = "cve"       // CVE-YYYY-NNNN
	KURL       Kind = "url"       // interesting URL
	KTech      Kind = "tech"      // web technology
	KLookalike Kind = "lookalike" // registered typo/homoglyph domain
	KIssue     Kind = "issue"     // a security problem (never recursed)
)

// Severity of a finding. Entities are usually SevInfo; issues carry the
// real rating.
type Severity int

const (
	SevInfo Severity = iota
	SevLow
	SevMedium
	SevHigh
	SevCritical
)

var sevNames = []string{"info", "low", "medium", "high", "critical"}

func (s Severity) String() string {
	if s < 0 || int(s) >= len(sevNames) {
		return "info"
	}
	return sevNames[s]
}

func (s Severity) MarshalText() ([]byte, error) { return []byte(s.String()), nil }

func (s *Severity) UnmarshalText(b []byte) error {
	for i, n := range sevNames {
		if n == string(b) {
			*s = Severity(i)
			return nil
		}
	}
	*s = SevInfo
	return nil
}

// Finding is the single, unified result format. It replaces the old
// "+ - !" text lines inside the engine; the UI renderer turns findings back
// into marker lines.
type Finding struct {
	Type       Kind              `json:"type"`
	Value      string            `json:"value"`
	Source     string            `json:"source"`           // data source, e.g. "crt.sh"
	Module     string            `json:"module,omitempty"` // module that produced it
	Time       time.Time         `json:"time"`
	Confidence int               `json:"confidence"` // 0..100
	Severity   Severity          `json:"severity"`
	Parent     string            `json:"parent,omitempty"` // Key() of the entity it came from
	Depth      int               `json:"depth"`
	Detail     string            `json:"detail,omitempty"` // one human-readable line
	Data       map[string]string `json:"data,omitempty"`
}

// Key identifies an entity independent of where it was found.
func (f Finding) Key() string { return string(f.Type) + ":" + strings.ToLower(f.Value) }

// IsEntity reports whether the finding can be fed into further modules.
func (f Finding) IsEntity() bool { return f.Type != KIssue }
