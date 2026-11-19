package main

// IP handling for IPv4 and IPv6 (ported from the 2.0.x enrichment branch
// into engine modules): canonical form, public/reserved filter, reverse DNS
// for in-addr.arpa and ip6.arpa, embedded IPv4 in transition addresses,
// EUI-64 interface IDs and an independent geolocation/ISP estimate.

import (
	"context"
	"encoding/hex"
	"fmt"
	"net"
	"strconv"
	"strings"
	"time"
)

// canonicalIP returns the canonical text form (lower case, compressed IPv6,
// IPv4-mapped IPv6 as plain IPv4) or "" if s is no IP address. Using it
// everywhere keeps "2001:DB8:0::1" and "2001:db8::1" one entity.
func canonicalIP(s string) string {
	ip := net.ParseIP(strings.Trim(strings.TrimSpace(s), "[]"))
	if ip == nil {
		return ""
	}
	return ip.String()
}

var reservedNets = func() []*net.IPNet {
	var ns []*net.IPNet
	for _, c := range []string{
		"0.0.0.0/8", "100.64.0.0/10", "192.0.0.0/24", "192.0.2.0/24", "198.18.0.0/15",
		"198.51.100.0/24", "203.0.113.0/24", "240.0.0.0/4",
		"2001:db8::/32", "100::/64", "fc00::/7",
	} {
		_, n, _ := net.ParseCIDR(c)
		ns = append(ns, n)
	}
	return ns
}()

// publicIP reports whether lookups about the address can return anything:
// private, loopback, link-local, CGNAT, documentation and other reserved
// ranges are skipped instead of wasting rate-limited API calls.
func publicIP(s string) bool {
	ip := net.ParseIP(s)
	if ip == nil || !ip.IsGlobalUnicast() || ip.IsPrivate() {
		return false
	}
	for _, n := range reservedNets {
		if n.Contains(ip) {
			return false
		}
	}
	return true
}

// reverseName builds the PTR query name: 4.3.2.1.in-addr.arpa or the
// 32-nibble ip6.arpa form.
func reverseName(s string) string {
	ip := net.ParseIP(s)
	if ip == nil {
		return ""
	}
	if v4 := ip.To4(); v4 != nil {
		return fmt.Sprintf("%d.%d.%d.%d.in-addr.arpa", v4[3], v4[2], v4[1], v4[0])
	}
	h := hex.EncodeToString(ip.To16())
	var b strings.Builder
	for i := len(h) - 1; i >= 0; i-- {
		b.WriteByte(h[i])
		b.WriteByte('.')
	}
	return b.String() + "ip6.arpa"
}

// v6Info describes what an IPv6 address reveals by its structure alone.
type v6Info struct {
	Kind     string // global unicast, 6to4, Teredo, NAT64 ...
	Embedded []struct{ IP, Role string }
	MAC      string // from an EUI-64 interface ID
}

func analyzeIPv6(s string) (v6Info, bool) {
	ip := net.ParseIP(s)
	if ip == nil || ip.To4() != nil {
		return v6Info{}, false
	}
	b := ip.To16()
	in := func(c string) bool { _, n, _ := net.ParseCIDR(c); return n.Contains(ip) }
	v4 := func(p []byte) string { return net.IPv4(p[0], p[1], p[2], p[3]).String() }
	var r v6Info
	add := func(ip, role string) { r.Embedded = append(r.Embedded, struct{ IP, Role string }{ip, role}) }
	switch {
	case in("2002::/16"):
		r.Kind = "6to4"
		add(v4(b[2:6]), "6to4 gateway")
	case in("2001::/32"):
		r.Kind = "Teredo"
		add(v4(b[4:8]), "Teredo server")
		add(v4([]byte{b[12] ^ 0xff, b[13] ^ 0xff, b[14] ^ 0xff, b[15] ^ 0xff}), "Teredo client (public NAT address)")
	case in("64:ff9b::/96"):
		r.Kind = "NAT64 (well-known prefix)"
		add(v4(b[12:16]), "NAT64 target")
	case in("2000::/3"):
		r.Kind = "global unicast"
	case in("fc00::/7"):
		r.Kind = "unique local (private)"
	case in("fe80::/10"):
		r.Kind = "link-local"
	case ip.IsMulticast():
		r.Kind = "multicast"
	default:
		r.Kind = "reserved / special purpose"
	}
	if r.Kind != "Teredo" && b[11] == 0xff && b[12] == 0xfe {
		r.MAC = net.HardwareAddr{b[8] ^ 0x02, b[9], b[10], b[13], b[14], b[15]}.String()
	}
	return r, true
}

var modIPv6 = &Module{
	Name: "ipv6", Desc: "IPv6 structure: 6to4/Teredo/NAT64 embedded IPv4, EUI-64 (offline)",
	In: []Kind{KIP}, Out: []Kind{KAttr, KIP},
	Run: func(ctx context.Context, in Finding, out *Out) error {
		r, ok := analyzeIPv6(in.Value)
		if !ok {
			return nil
		}
		out.Add(Finding{Type: KAttr, Value: "IPv6 type: " + r.Kind, Source: "offline", Confidence: 100})
		for _, e := range r.Embedded {
			out.Add(Finding{Type: KIP, Value: e.IP, Source: "offline", Confidence: 95,
				Detail: e.Role + " embedded in " + in.Value, Data: map[string]string{"relation": e.Role}})
		}
		if r.MAC != "" {
			out.Add(Finding{Type: KAttr, Value: "EUI-64 interface ID, MAC " + r.MAC, Source: "offline", Confidence: 90,
				Detail: "SLAAC address derived from the hardware address (no privacy extensions)"})
		}
		return nil
	},
}

var modRDNS = &Module{
	Name: "rdns", Desc: "Reverse DNS (PTR) for IPv4 and IPv6 via DoH",
	In: []Kind{KIP}, Out: []Kind{KHost}, Timeout: 15 * time.Second, Retries: 1,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		if !publicIP(in.Value) {
			return nil
		}
		r, err := dohLookup(ctx, reverseName(in.Value), "PTR")
		if err != nil {
			return err
		}
		for _, a := range r.Answers {
			if h := strings.ToLower(a.Data); domainRe.MatchString(h) {
				out.Add(Finding{Type: KHost, Value: h, Source: "rdns", Confidence: 90, Detail: "PTR of " + in.Value,
					Data: map[string]string{"rr": "PTR"}})
			}
		}
		return nil
	},
}

// ipwho.is: an independent second opinion on location and operator. The
// location of an IP is the operator's network, never a person's position.
var modIPWhois = &Module{
	Name: "ipwhois", Desc: "IP geolocation estimate + ISP (ipwho.is, free)",
	In: []Kind{KIP}, Out: []Kind{KAttr}, Timeout: 15 * time.Second, Retries: 1, Rate: time.Second,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		if !publicIP(in.Value) {
			return nil
		}
		var r struct {
			IP          string  `json:"ip"`
			Success     bool    `json:"success"`
			Country     string  `json:"country"`
			CountryCode string  `json:"country_code"`
			Region      string  `json:"region"`
			City        string  `json:"city"`
			Lat         float64 `json:"latitude"`
			Lon         float64 `json:"longitude"`
			Connection  struct {
				ASN int    `json:"asn"`
				Org string `json:"org"`
				ISP string `json:"isp"`
			} `json:"connection"`
			Timezone struct {
				ID string `json:"id"`
			} `json:"timezone"`
		}
		if err := getJSON(ctx, "https://ipwho.is/"+in.Value, nil, 7*day, &r); err != nil {
			return err
		}
		// Only accept an answer for exactly this address.
		if !r.Success || canonicalIP(r.IP) != canonicalIP(in.Value) {
			return fmt.Errorf("%w: no match", errPermanent)
		}
		if place := strings.Join(filterEmpty(r.City, r.Region, r.Country), ", "); place != "" {
			out.Add(Finding{Type: KAttr, Value: "Location estimate: " + place, Source: "ipwhois", Confidence: 50,
				Detail: "network location, approximate", Data: map[string]string{
					"country": r.CountryCode, "lat": strconv.FormatFloat(r.Lat, 'f', 4, 64), "lon": strconv.FormatFloat(r.Lon, 'f', 4, 64)}})
		}
		isp := r.Connection.ISP
		if isp == "" {
			isp = r.Connection.Org
		}
		if isp != "" {
			d := ""
			if r.Connection.ASN > 0 {
				d = "AS" + strconv.Itoa(r.Connection.ASN)
			}
			out.Add(Finding{Type: KAttr, Value: "ISP: " + isp, Source: "ipwhois", Confidence: 70, Detail: d})
		}
		if r.Timezone.ID != "" {
			out.Add(Finding{Type: KAttr, Value: "Time zone: " + r.Timezone.ID, Source: "ipwhois", Confidence: 50})
		}
		return nil
	},
}
