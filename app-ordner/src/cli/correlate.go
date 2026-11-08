package main

import (
	"net"
	"sort"
	"strings"
)

// ---------------------------------------------------------------------------
// Correlation + entity graph.
//
// This is the idea borrowed from SpiderFoot, Recon-ng and Maltego: instead of
// just listing what each probe found, cross-reference the entities (domains,
// subdomains, IPs, operators/ASNs, netblocks, services) and show how they link
// together. It operates ONLY on infrastructure entities - never on people.
// ---------------------------------------------------------------------------

func correlate(domain string, ips []string, ipHosts map[string][]string, data []*ipData, liveOpen [][]int) {
	head("Correlations")

	// Index the enriched data by IP for easy lookup.
	byIP := map[string]*ipData{}
	for i, ip := range ips {
		if i < len(data) && data[i] != nil {
			byIP[ip] = data[i]
		}
	}

	// 1) Operator / ASN spread: how concentrated is the estate?
	type grp struct {
		label string
		n     int
	}
	opCount := map[string]int{}
	for _, ip := range ips {
		d := byIP[ip]
		if d == nil {
			continue
		}
		label := strings.TrimSpace(d.org)
		if d.asn != "" {
			label = d.asn + " " + label
		}
		if label == "" {
			label = "unknown"
		}
		opCount[strings.TrimSpace(label)]++
	}
	if len(opCount) > 0 {
		var ops []grp
		for l, n := range opCount {
			ops = append(ops, grp{l, n})
		}
		sort.Slice(ops, func(i, j int) bool { return ops[i].n > ops[j].n })
		var parts []string
		for i, o := range ops {
			if i >= 4 {
				break
			}
			parts = append(parts, shorten(o.label, 28)+" ("+itoa(o.n)+")")
		}
		found("Estate spans %d operator(s): %s", len(opCount), strings.Join(parts, ", "))
	}

	// 2) Shared hosting: one IP serving several subdomains.
	type share struct {
		ip string
		n  int
	}
	var shared []share
	for ip, hosts := range ipHosts {
		if len(hosts) > 1 {
			shared = append(shared, share{ip, len(hosts)})
		}
	}
	sort.Slice(shared, func(i, j int) bool { return shared[i].n > shared[j].n })
	for i, s := range shared {
		if i >= 3 {
			info("... and %d more shared-hosting IPs", len(shared)-3)
			break
		}
		found("Shared hosting: %s serves %d subdomains", s.ip, s.n)
	}
	if len(shared) == 0 {
		info("No shared-hosting IP (each host on its own address)")
	}

	// 3) Netblock grouping (/24): adjacent addresses hint at one environment.
	blocks := map[string][]string{}
	for _, ip := range ips {
		if p := net.ParseIP(ip).To4(); p != nil {
			key := itoa(int(p[0])) + "." + itoa(int(p[1])) + "." + itoa(int(p[2])) + ".0/24"
			blocks[key] = append(blocks[key], ip)
		}
	}
	var bigBlocks []grp
	for k, v := range blocks {
		if len(v) > 1 {
			bigBlocks = append(bigBlocks, grp{k, len(v)})
		}
	}
	sort.Slice(bigBlocks, func(i, j int) bool { return bigBlocks[i].n > bigBlocks[j].n })
	for i, b := range bigBlocks {
		if i >= 3 {
			break
		}
		info("Netblock %s holds %d of the mapped IPs", b.label, b.n)
	}

	// 4) Service exposure rollup: which ports recur across the estate.
	portCount := map[int]int{}
	for i := range ips {
		seen := map[int]bool{}
		if i < len(liveOpen) {
			for _, p := range liveOpen[i] {
				seen[p] = true
			}
		}
		if d := byIP[ips[i]]; d != nil {
			for _, p := range d.ports {
				seen[p] = true
			}
		}
		for p := range seen {
			portCount[p]++
		}
	}
	if len(portCount) > 0 {
		type pc struct{ port, n int }
		var pcs []pc
		for p, n := range portCount {
			pcs = append(pcs, pc{p, n})
		}
		sort.Slice(pcs, func(i, j int) bool {
			if pcs[i].n != pcs[j].n {
				return pcs[i].n > pcs[j].n
			}
			return pcs[i].port < pcs[j].port
		})
		var parts []string
		for i, p := range pcs {
			if i >= 5 {
				break
			}
			lbl := itoa(p.port)
			if s := wellKnownPort[p.port]; s != "" {
				lbl += "/" + s
			}
			parts = append(parts, lbl+" x"+itoa(p.n))
		}
		info("Common services: %s", strings.Join(parts, ", "))
	}

	// 5) Vulnerable-host rollup.
	var vulnHosts []string
	for _, ip := range ips {
		if d := byIP[ip]; d != nil && len(d.vulns) > 0 {
			vulnHosts = append(vulnHosts, ip+" ("+itoa(len(d.vulns))+")")
		}
	}
	if len(vulnHosts) > 0 {
		if len(vulnHosts) > 4 {
			vulnHosts = vulnHosts[:4]
		}
		warn("Hosts with known CVEs: %s", strings.Join(vulnHosts, ", "))
	}

	// 6) Pivot candidates: reverse-DNS names that point OUTSIDE the target
	//    domain are related infrastructure worth a follow-up lookup (the
	//    Maltego "transform into a new entity" idea - for domains, not people).
	var pivots []string
	seenPivot := map[string]bool{}
	for _, ip := range ips {
		d := byIP[ip]
		if d == nil || d.rdns == "" {
			continue
		}
		r := strings.TrimSuffix(strings.ToLower(d.rdns), ".")
		if r == domain || strings.HasSuffix(r, "."+domain) {
			continue
		}
		reg := registrableDomain(r)
		if reg != "" && !seenPivot[reg] {
			seenPivot[reg] = true
			pivots = append(pivots, reg)
		}
	}
	if len(pivots) > 0 {
		if len(pivots) > 6 {
			pivots = pivots[:6]
		}
		found("Related domains via rDNS (pivot): %s", shorten(strings.Join(pivots, ", "), 84))
	}

	// -----------------------------------------------------------------------
	// Entity graph (Maltego-style, drawn as text): domain -> operator -> IP -> hosts
	// -----------------------------------------------------------------------
	head("Entity graph")
	found("%s", domain)
	// Group the mapped IPs under their operator.
	opIPs := map[string][]string{}
	for _, ip := range ips {
		d := byIP[ip]
		label := "unknown operator"
		if d != nil {
			label = strings.TrimSpace(d.asn + " " + d.org)
			if label == "" {
				label = "unknown operator"
			}
		}
		opIPs[label] = append(opIPs[label], ip)
	}
	var opNames []string
	for l := range opIPs {
		opNames = append(opNames, l)
	}
	sort.Slice(opNames, func(i, j int) bool { return len(opIPs[opNames[i]]) > len(opIPs[opNames[j]]) })
	for _, op := range opNames {
		info("  %s", shorten(op, 38))
		list := opIPs[op]
		sort.Strings(list)
		for i, ip := range list {
			if i >= 4 {
				info("      +%d more IP(s)", len(list)-4)
				break
			}
			hosts := ipHosts[ip]
			h := strings.Join(hosts, ", ")
			if len(hosts) > 2 {
				h = strings.Join(hosts[:2], ", ") + " +" + itoa(len(hosts)-2)
			}
			info("      %s  %s", ip, shorten(h, 30))
		}
	}
}

// registrableDomain returns the last two labels of a host (a rough eTLD+1).
func registrableDomain(host string) string {
	host = strings.Trim(host, ".")
	parts := strings.Split(host, ".")
	if len(parts) < 2 {
		return ""
	}
	return strings.Join(parts[len(parts)-2:], ".")
}
