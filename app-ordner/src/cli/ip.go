package main

import (
	"encoding/json"
	"net"
	"strings"
)

func runIP(raw string) {
	ip := net.ParseIP(strings.TrimSpace(raw))
	head("IP-CHECK: %s", raw)
	if ip == nil {
		warn("KEINE GUELTIGE IP-ADRESSE")
		return
	}
	if ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() || ip.IsUnspecified() {
		info("PRIVATE/LOKALE ADRESSE: KEINE OEFFENTLICHEN DATEN")
		return
	}
	found("OEFFENTLICHE ADRESSE (%s)", map[bool]string{true: "IPV4", false: "IPV6"}[ip.To4() != nil])

	ctx, cancel := dnsCtx(6)
	names, err := net.DefaultResolver.LookupAddr(ctx, ip.String())
	cancel()
	if err == nil && len(names) > 0 {
		found("RDNS: %s", strings.TrimSuffix(names[0], "."))
	} else {
		miss("KEIN RDNS-EINTRAG")
	}

	head("NETZ")
	if resp, body, err := get(client, "https://ipinfo.io/"+ip.String()+"/json"); err != nil || resp.StatusCode != 200 {
		warn("IPINFO NICHT ERREICHBAR")
	} else {
		var d struct {
			Org      string `json:"org"`
			Country  string `json:"country"`
			Timezone string `json:"timezone"`
		}
		if json.Unmarshal(body, &d) == nil {
			if d.Org != "" {
				found("BETREIBER (ASN): %s", shorten(d.Org, 70))
			}
			if d.Country != "" {
				found("LAND: %s", d.Country)
			}
			if d.Timezone != "" {
				info("ZEITZONE: %s", d.Timezone)
			}
		}
	}

	head("OFFENE DIENSTE (SHODAN INTERNETDB)")
	resp, body, err := get(client, "https://internetdb.shodan.io/"+ip.String())
	if err != nil {
		warn("INTERNETDB NICHT ERREICHBAR")
		return
	}
	if resp.StatusCode == 404 {
		miss("KEINE DATEN ZU DIESER ADRESSE")
		return
	}
	var db struct {
		Ports     []int    `json:"ports"`
		Hostnames []string `json:"hostnames"`
		Tags      []string `json:"tags"`
		Vulns     []string `json:"vulns"`
	}
	if resp.StatusCode != 200 || json.Unmarshal(body, &db) != nil {
		warn("INTERNETDB: HTTP %d", resp.StatusCode)
		return
	}
	if len(db.Ports) > 0 {
		var ps []string
		for _, p := range db.Ports {
			ps = append(ps, itoa(p))
		}
		found("PORTS: %s", strings.Join(ps, ", "))
	} else {
		miss("KEINE OFFENEN PORTS BEKANNT")
	}
	if len(db.Hostnames) > 0 {
		info("HOSTNAMES: %s", shorten(strings.Join(db.Hostnames, ", "), 90))
	}
	if len(db.Tags) > 0 {
		info("TAGS: %s", strings.Join(db.Tags, ", "))
	}
	if len(db.Vulns) > 0 {
		v := db.Vulns
		if len(v) > 8 {
			v = v[:8]
		}
		warn("BEKANNTE SCHWACHSTELLEN (%d): %s", len(db.Vulns), strings.Join(v, ", "))
	}
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	s := ""
	for n > 0 {
		s = string(rune('0'+n%10)) + s
		n /= 10
	}
	return s
}
