package main

import (
	"crypto/md5"
	"encoding/hex"
	"net"
	"regexp"
	"strings"
)

var emailRe = regexp.MustCompile(`^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$`)

var roleAccounts = map[string]bool{
	"info": true, "admin": true, "administrator": true, "support": true, "sales": true,
	"contact": true, "kontakt": true, "office": true, "mail": true, "noreply": true,
	"no-reply": true, "postmaster": true, "abuse": true, "webmaster": true, "hostmaster": true,
	"security": true, "service": true, "hello": true, "team": true, "billing": true, "jobs": true,
	"hr": true, "marketing": true, "press": true, "presse": true, "empfang": true,
}

var freeProviders = map[string]string{
	"gmail.com": "Google Gmail", "googlemail.com": "Google Gmail", "outlook.com": "Microsoft Outlook",
	"hotmail.com": "Microsoft Hotmail", "live.com": "Microsoft Live", "yahoo.com": "Yahoo",
	"yahoo.de": "Yahoo", "gmx.de": "GMX", "gmx.net": "GMX", "gmx.at": "GMX", "gmx.ch": "GMX",
	"web.de": "WEB.DE", "t-online.de": "T-Online", "icloud.com": "Apple iCloud", "me.com": "Apple",
	"proton.me": "Proton", "protonmail.com": "Proton", "pm.me": "Proton", "mailbox.org": "mailbox.org",
	"posteo.de": "Posteo", "freenet.de": "freenet", "aol.com": "AOL", "zoho.com": "Zoho",
	"tutanota.com": "Tuta", "tuta.io": "Tuta", "tutamail.com": "Tuta", "msn.com": "Microsoft MSN",
}

var disposableDomains = map[string]bool{
	"mailinator.com": true, "guerrillamail.com": true, "guerrillamail.net": true, "10minutemail.com": true,
	"tempmail.com": true, "temp-mail.org": true, "trashmail.com": true, "yopmail.com": true,
	"throwawaymail.com": true, "getnada.com": true, "sharklasers.com": true, "maildrop.cc": true,
	"dispostable.com": true, "fakeinbox.com": true, "mailnesia.com": true, "moakt.com": true,
	"tempail.com": true, "mohmal.com": true, "emailondeck.com": true, "spamgourmet.com": true,
	"mintemail.com": true, "mytemp.email": true, "burnermail.io": true, "einrot.com": true,
	"wegwerfemail.de": true, "wegwerfmail.de": true, "trash-mail.com": true, "discard.email": true,
}

// Detect the provider from the mail server.
var mxProviders = []struct{ suffix, name string }{
	{"google.com.", "Google Workspace / Gmail"},
	{"googlemail.com.", "Google Workspace / Gmail"},
	{"protection.outlook.com.", "Microsoft 365"},
	{"outlook.com.", "Microsoft Outlook"},
	{"pphosted.com.", "Proofpoint (mail filter)"},
	{"mimecast.com.", "Mimecast (mail filter)"},
	{"protonmail.ch.", "Proton"},
	{"proton.me.", "Proton"},
	{"icloud.com.", "Apple iCloud"},
	{"yahoodns.net.", "Yahoo"},
	{"kundenserver.de.", "IONOS / 1&1"},
	{"ionos.de.", "IONOS"},
	{"ionos.com.", "IONOS"},
	{"web.de.", "WEB.DE"},
	{"gmx.net.", "GMX"},
	{"t-online.de.", "T-Online"},
	{"zoho.com.", "Zoho"},
	{"zoho.eu.", "Zoho"},
	{"mailbox.org.", "mailbox.org"},
	{"secureserver.net.", "GoDaddy"},
	{"hostinger.com.", "Hostinger"},
	{"strato.de.", "STRATO"},
	{"hetzner.com.", "Hetzner"},
	{"your-server.de.", "Hetzner"},
}

func runEmail(addr string) {
	addr = strings.TrimSpace(addr)
	head("Email check: %s", addr)
	if !emailRe.MatchString(addr) {
		warn("Invalid syntax (expected: name@domain.tld)")
		return
	}
	found("Syntax valid")
	at := strings.LastIndex(addr, "@")
	local, domain := addr[:at], strings.ToLower(addr[at+1:])

	// Local part
	base := strings.ToLower(local)
	if i := strings.Index(base, "+"); i > 0 {
		info("Plus addressing: tag '%s', base '%s'", base[i+1:], base[:i])
		base = base[:i]
	}
	if roleAccounts[base] {
		info("Role account (%s), not a person", base)
	}

	// Domain type
	if p, ok := freeProviders[domain]; ok {
		info("Free provider: %s", p)
	}
	if disposableDomains[domain] {
		warn("Disposable address (throwaway mailbox)")
	}

	// Mail server
	head("Mail server")
	ctx, cancel := dnsCtx(6)
	mxs, err := net.DefaultResolver.LookupMX(ctx, domain)
	cancel()
	if err != nil || len(mxs) == 0 {
		warn("No MX record: domain may not accept mail")
		if len(ipsOf(domain)) == 0 {
			warn("Domain does not resolve")
		}
	} else {
		provider := ""
		for i, mx := range mxs {
			if i < 5 {
				found("MX %d: %s", mx.Pref, strings.TrimSuffix(mx.Host, "."))
			}
			for _, p := range mxProviders {
				if strings.HasSuffix(strings.ToLower(mx.Host), p.suffix) {
					provider = p.name
				}
			}
		}
		if provider != "" {
			info("Mail provider: %s", provider)
		}
	}

	// SPF / DMARC
	spf, dmarc := "", ""
	ctx, cancel = dnsCtx(6)
	txts, _ := net.DefaultResolver.LookupTXT(ctx, domain)
	cancel()
	for _, t := range txts {
		if strings.HasPrefix(strings.ToLower(t), "v=spf1") {
			spf = t
		}
	}
	ctx, cancel = dnsCtx(6)
	dtxts, _ := net.DefaultResolver.LookupTXT(ctx, "_dmarc."+domain)
	cancel()
	for _, t := range dtxts {
		if strings.HasPrefix(strings.ToUpper(t), "V=DMARC1") {
			dmarc = t
		}
	}
	if spf != "" {
		found("SPF: %s", shorten(spf, 90))
	} else {
		miss("SPF: no record")
	}
	if dmarc != "" {
		found("DMARC: %s", shorten(dmarc, 90))
	} else {
		miss("DMARC: no record")
	}

	// Gravatar (only whether an image exists)
	head("Public traces")
	sum := md5.Sum([]byte(strings.ToLower(addr)))
	gurl := "https://www.gravatar.com/avatar/" + hex.EncodeToString(sum[:]) + "?d=404"
	if resp, _, err := get(client, gurl); err != nil {
		warn("Gravatar: no response")
	} else if resp.StatusCode == 200 {
		found("Gravatar: profile picture exists")
	} else if resp.StatusCode == 404 {
		miss("Gravatar: no profile picture")
	} else {
		warn("Gravatar: HTTP %d", resp.StatusCode)
	}

	// Domain registration (not for free providers)
	if _, free := freeProviders[domain]; !free {
		head("Domain %s", domain)
		rdapSummary(domain)
	}
	info("No mailbox check (no contact with the mail server)")
}
