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
	"gmail.com": "GOOGLE GMAIL", "googlemail.com": "GOOGLE GMAIL", "outlook.com": "MICROSOFT OUTLOOK",
	"hotmail.com": "MICROSOFT HOTMAIL", "live.com": "MICROSOFT LIVE", "yahoo.com": "YAHOO",
	"yahoo.de": "YAHOO", "gmx.de": "GMX", "gmx.net": "GMX", "gmx.at": "GMX", "gmx.ch": "GMX",
	"web.de": "WEB.DE", "t-online.de": "T-ONLINE", "icloud.com": "APPLE ICLOUD", "me.com": "APPLE",
	"proton.me": "PROTON", "protonmail.com": "PROTON", "pm.me": "PROTON", "mailbox.org": "MAILBOX.ORG",
	"posteo.de": "POSTEO", "freenet.de": "FREENET", "aol.com": "AOL", "zoho.com": "ZOHO",
	"tutanota.com": "TUTA", "tuta.io": "TUTA", "tutamail.com": "TUTA", "msn.com": "MICROSOFT MSN",
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

// Anbieter anhand des Mailservers erkennen.
var mxProviders = []struct{ suffix, name string }{
	{"google.com.", "GOOGLE WORKSPACE / GMAIL"},
	{"googlemail.com.", "GOOGLE WORKSPACE / GMAIL"},
	{"protection.outlook.com.", "MICROSOFT 365"},
	{"outlook.com.", "MICROSOFT OUTLOOK"},
	{"pphosted.com.", "PROOFPOINT (MAIL-FILTER)"},
	{"mimecast.com.", "MIMECAST (MAIL-FILTER)"},
	{"protonmail.ch.", "PROTON"},
	{"proton.me.", "PROTON"},
	{"icloud.com.", "APPLE ICLOUD"},
	{"yahoodns.net.", "YAHOO"},
	{"kundenserver.de.", "IONOS / 1&1"},
	{"ionos.de.", "IONOS"},
	{"ionos.com.", "IONOS"},
	{"web.de.", "WEB.DE"},
	{"gmx.net.", "GMX"},
	{"t-online.de.", "T-ONLINE"},
	{"zoho.com.", "ZOHO"},
	{"zoho.eu.", "ZOHO"},
	{"mailbox.org.", "MAILBOX.ORG"},
	{"secureserver.net.", "GODADDY"},
	{"hostinger.com.", "HOSTINGER"},
	{"strato.de.", "STRATO"},
	{"hetzner.com.", "HETZNER"},
	{"your-server.de.", "HETZNER"},
}

func runEmail(addr string) {
	addr = strings.TrimSpace(addr)
	head("E-MAIL-CHECK: %s", addr)
	if !emailRe.MatchString(addr) {
		warn("UNGUELTIGE SYNTAX (ERWARTET: NAME@DOMAIN.TLD)")
		return
	}
	found("SYNTAX GUELTIG")
	at := strings.LastIndex(addr, "@")
	local, domain := addr[:at], strings.ToLower(addr[at+1:])

	// Lokaler Teil
	base := strings.ToLower(local)
	if i := strings.Index(base, "+"); i > 0 {
		info("PLUS-ADRESSIERUNG: TAG '%s', BASIS '%s'", base[i+1:], base[:i])
		base = base[:i]
	}
	if roleAccounts[base] {
		info("FUNKTIONSADRESSE (%s), KEINE PERSON", base)
	}

	// Domain-Art
	if p, ok := freeProviders[domain]; ok {
		info("KOSTENLOSER ANBIETER: %s", p)
	}
	if disposableDomains[domain] {
		warn("WEGWERF-ADRESSE (EINMAL-MAILBOX)")
	}

	// Mailserver
	head("MAILSERVER")
	ctx, cancel := dnsCtx(6)
	mxs, err := net.DefaultResolver.LookupMX(ctx, domain)
	cancel()
	if err != nil || len(mxs) == 0 {
		warn("KEIN MX-EINTRAG: DOMAIN NIMMT EVTL. KEINE MAILS AN")
		if len(ipsOf(domain)) == 0 {
			warn("DOMAIN LOEST NICHT AUF")
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
			info("MAIL-ANBIETER: %s", provider)
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
		miss("SPF: KEIN EINTRAG")
	}
	if dmarc != "" {
		found("DMARC: %s", shorten(dmarc, 90))
	} else {
		miss("DMARC: KEIN EINTRAG")
	}

	// Gravatar (nur Existenz des Bildes)
	head("OEFFENTLICHE SPUREN")
	sum := md5.Sum([]byte(strings.ToLower(addr)))
	gurl := "https://www.gravatar.com/avatar/" + hex.EncodeToString(sum[:]) + "?d=404"
	if resp, _, err := get(client, gurl); err != nil {
		warn("GRAVATAR: KEINE ANTWORT")
	} else if resp.StatusCode == 200 {
		found("GRAVATAR: PROFILBILD VORHANDEN")
	} else if resp.StatusCode == 404 {
		miss("GRAVATAR: KEIN PROFILBILD")
	} else {
		warn("GRAVATAR: HTTP %d", resp.StatusCode)
	}

	// Domain-Registrierung (nicht fuer kostenlose Anbieter)
	if _, free := freeProviders[domain]; !free {
		head("DOMAIN %s", domain)
		rdapSummary(domain)
	}
	info("KEINE POSTFACH-PRUEFUNG (KEIN KONTAKT ZUM MAILSERVER)")
}
