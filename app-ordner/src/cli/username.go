package main

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
	"sync"
)

// Check modes:
//
//	status      200 = found, 404/410 (and optionally arg as code) = not found
//	notbody     200 and body != arg = found
//	notcontains 200 and body does NOT contain arg = found
//	contains    200 and body contains arg = found
type site struct {
	name, url, mode, arg, cat string
}

// Only platforms with a reliable public existence signal are listed. Sites
// that return the same page for every name, or that block automated requests
// (most large social networks), are deliberately left out so a hit means
// something.
var sites = []site{
	// Code / developer
	{"GitHub", "https://github.com/{u}", "status", "", "dev"},
	{"GitLab", "https://gitlab.com/api/v4/users?username={u}", "notbody", "[]", "dev"},
	{"Codeberg", "https://codeberg.org/{u}", "status", "", "dev"},
	{"Bitbucket", "https://bitbucket.org/{u}/", "status", "", "dev"},
	{"SourceForge", "https://sourceforge.net/u/{u}/profile", "status", "", "dev"},
	{"Launchpad", "https://launchpad.net/~{u}", "status", "", "dev"},
	{"DockerHub", "https://hub.docker.com/v2/users/{u}/", "status", "", "dev"},
	{"PyPI", "https://pypi.org/user/{u}/", "status", "", "dev"},
	{"NPM", "https://www.npmjs.com/~{u}", "status", "", "dev"},
	{"RubyGems", "https://rubygems.org/profiles/{u}", "status", "", "dev"},
	{"Crates.io", "https://crates.io/api/v1/users/{u}", "status", "", "dev"},
	{"Packagist", "https://packagist.org/users/{u}/", "status", "", "dev"},
	{"NuGet", "https://www.nuget.org/profiles/{u}", "status", "", "dev"},
	{"DEV.to", "https://dev.to/api/users/by_username?url={u}", "status", "", "dev"},
	{"Hashnode", "https://hashnode.com/@{u}", "status", "", "dev"},
	{"Replit", "https://replit.com/@{u}", "status", "", "dev"},
	{"Kaggle", "https://www.kaggle.com/{u}", "status", "", "dev"},
	{"Keybase", "https://keybase.io/_/api/1.0/user/lookup.json?usernames={u}&fields=basics", "contains", "\"basics\"", "dev"},
	{"StackOverflow", "https://api.stackexchange.com/2.3/users?inname={u}&site=stackoverflow", "notcontains", "\"items\":[]", "dev"},

	// Security / hacking
	{"HackerOne", "https://hackerone.com/{u}", "status", "", "security"},
	{"TryHackMe", "https://tryhackme.com/p/{u}", "status", "", "security"},
	{"Exploit.in", "https://gitlab.com/api/v4/users?username={u}", "notbody", "[]", "security"},

	// Writing / blogging
	{"Medium", "https://medium.com/@{u}", "status", "", "writing"},
	{"WordPress", "https://{u}.wordpress.com", "status", "", "writing"},
	{"Blogspot", "https://{u}.blogspot.com", "status", "", "writing"},
	{"Tumblr", "https://{u}.tumblr.com", "status", "", "writing"},
	{"Substack", "https://{u}.substack.com", "status", "", "writing"},
	{"Pastebin", "https://pastebin.com/u/{u}", "status", "", "writing"},
	{"ProductHunt", "https://www.producthunt.com/@{u}", "status", "", "writing"},

	// Social / community
	{"Reddit", "https://www.reddit.com/user/{u}/about.json", "status", "", "social"},
	{"Mastodon.social", "https://mastodon.social/@{u}", "status", "", "social"},
	{"Fosstodon", "https://fosstodon.org/@{u}", "status", "", "social"},
	{"Bluesky", "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor={u}.bsky.social", "status", "400", "social"},
	{"HackerNews", "https://hacker-news.firebaseio.com/v0/user/{u}.json", "notbody", "null", "social"},
	{"Keyoxide", "https://keyoxide.org/{u}", "status", "", "social"},
	{"OpenStreetMap", "https://www.openstreetmap.org/user/{u}", "status", "", "social"},
	{"Gravatar", "https://en.gravatar.com/{u}.json", "status", "", "social"},
	{"Wikipedia(EN)", "https://en.wikipedia.org/w/api.php?action=query&list=users&ususers={u}&format=json", "notcontains", "\"missing\"", "social"},
	{"Linktree", "https://linktr.ee/{u}", "status", "", "social"},
	{"About.me", "https://about.me/{u}", "status", "", "social"},
	{"Carrd", "https://{u}.carrd.co", "status", "", "social"},

	// Creative / design / photo
	{"Behance", "https://www.behance.net/{u}", "status", "", "creative"},
	{"Dribbble", "https://dribbble.com/{u}", "status", "", "creative"},
	{"DeviantArt", "https://www.deviantart.com/{u}", "status", "", "creative"},
	{"500px", "https://500px.com/p/{u}", "status", "", "creative"},
	{"Unsplash", "https://unsplash.com/@{u}", "status", "", "creative"},
	{"Flickr", "https://www.flickr.com/people/{u}/", "status", "", "creative"},
	{"Pinterest", "https://www.pinterest.com/{u}/", "status", "", "creative"},
	{"Instructables", "https://www.instructables.com/member/{u}/", "status", "", "creative"},

	// Music / audio
	{"SoundCloud", "https://soundcloud.com/{u}", "status", "", "music"},
	{"Bandcamp", "https://{u}.bandcamp.com", "status", "", "music"},
	{"Mixcloud", "https://api.mixcloud.com/{u}/", "status", "", "music"},
	{"Last.fm", "https://www.last.fm/user/{u}", "status", "", "music"},
	{"Genius", "https://genius.com/{u}", "status", "", "music"},

	// Video
	{"YouTube", "https://www.youtube.com/@{u}", "status", "", "video"},
	{"Vimeo", "https://vimeo.com/{u}", "status", "", "video"},
	{"Dailymotion", "https://www.dailymotion.com/{u}", "status", "", "video"},

	// Gaming
	{"Steam", "https://steamcommunity.com/id/{u}", "notcontains", "The specified profile could not be found", "gaming"},
	{"Lichess", "https://lichess.org/api/user/{u}", "status", "", "gaming"},
	{"Chess.com", "https://api.chess.com/pub/player/{u}", "status", "", "gaming"},
	{"Codeforces", "https://codeforces.com/api/user.info?handles={u}", "status", "400", "gaming"},
	{"Speedrun", "https://www.speedrun.com/api/v1/users?lookup={u}", "notcontains", "\"data\":[]", "gaming"},
	{"osu!", "https://osu.ppy.sh/users/{u}", "status", "", "gaming"},
	{"Itch.io", "https://{u}.itch.io/", "status", "", "gaming"},

	// Film / books / hobbies
	{"Letterboxd", "https://letterboxd.com/{u}/", "status", "", "hobby"},
	{"Trakt", "https://trakt.tv/users/{u}", "status", "", "hobby"},
	{"MyAnimeList", "https://myanimelist.net/profile/{u}", "status", "", "hobby"},
	{"Untappd", "https://untappd.com/user/{u}", "status", "", "hobby"},

	// Support the creator / commerce
	{"Patreon", "https://www.patreon.com/{u}", "status", "", "commerce"},
	{"Ko-fi", "https://ko-fi.com/{u}", "status", "", "commerce"},
	{"BuyMeACoffee", "https://www.buymeacoffee.com/{u}", "status", "", "commerce"},
	{"Gumroad", "https://{u}.gumroad.com", "status", "", "commerce"},
	{"OpenCollective", "https://opencollective.com/{u}", "status", "", "commerce"},
	{"Slideshare", "https://www.slideshare.net/{u}", "status", "", "commerce"},
}

var validUser = regexp.MustCompile(`^[A-Za-z0-9._-]{2,40}$`)

const (
	stFound = iota
	stMissing
	stUnknown
)

type siteResult struct {
	s     site
	state int
	url   string
	note  string
}

func checkSite(s site, user string) siteResult {
	url := strings.ReplaceAll(s.url, "{u}", user)
	r := siteResult{s: s, url: profileURL(s, user), state: stUnknown}
	resp, body, err := get(client, url)
	if err != nil {
		r.note = "no response"
		return r
	}
	code := resp.StatusCode
	text := strings.TrimSpace(string(body))
	switch s.mode {
	case "status":
		switch {
		case code == 200:
			r.state = stFound
		case code == 404 || code == 410 || (s.arg == "400" && code == 400):
			r.state = stMissing
		default:
			r.note = fmt.Sprintf("HTTP %d", code)
		}
	case "notbody":
		switch {
		case code == 200 && text != s.arg:
			r.state = stFound
		case code == 200 || code == 404:
			r.state = stMissing
		default:
			r.note = fmt.Sprintf("HTTP %d", code)
		}
	case "notcontains":
		switch {
		case code == 200 && !strings.Contains(text, s.arg):
			r.state = stFound
		case code == 200 || code == 404:
			r.state = stMissing
		default:
			r.note = fmt.Sprintf("HTTP %d", code)
		}
	case "contains":
		switch {
		case code == 200 && strings.Contains(text, s.arg):
			r.state = stFound
		case code == 200 || code == 404:
			r.state = stMissing
		default:
			r.note = fmt.Sprintf("HTTP %d", code)
		}
	}
	return r
}

// profileURL returns the human-readable profile URL (instead of the API URL).
func profileURL(s site, user string) string {
	switch s.name {
	case "GitLab", "Exploit.in":
		return "https://gitlab.com/" + user
	case "HackerNews":
		return "https://news.ycombinator.com/user?id=" + user
	case "DEV.to":
		return "https://dev.to/" + user
	case "DockerHub":
		return "https://hub.docker.com/u/" + user
	case "Keybase":
		return "https://keybase.io/" + user
	case "Lichess":
		return "https://lichess.org/@/" + user
	case "Chess.com":
		return "https://www.chess.com/member/" + user
	case "Codeforces":
		return "https://codeforces.com/profile/" + user
	case "Bluesky":
		return "https://bsky.app/profile/" + user + ".bsky.social"
	case "Gravatar":
		return "https://gravatar.com/" + user
	case "Wikipedia(EN)":
		return "https://en.wikipedia.org/wiki/User:" + user
	case "Reddit":
		return "https://www.reddit.com/user/" + user
	case "Crates.io":
		return "https://crates.io/users/" + user
	case "Speedrun":
		return "https://www.speedrun.com/" + user
	case "Mixcloud":
		return "https://www.mixcloud.com/" + user + "/"
	case "StackOverflow":
		return "https://stackoverflow.com/users?filter=" + user
	}
	return strings.ReplaceAll(s.url, "{u}", user)
}

func runUsername(u string) {
	if !validUser.MatchString(u) {
		warn("Invalid username (2-40 characters: a-z 0-9 . _ -)")
		return
	}
	head("Username check: %s", u)
	store.Scope(KindAccount, u)
	info("Checking %d public platforms ...", len(sites))
	info("Hit = name is taken there, not necessarily the same person")

	results := make(chan siteResult, len(sites))
	sem := make(chan struct{}, 12)
	var wg sync.WaitGroup
	for _, s := range sites {
		wg.Add(1)
		go func(s site) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			results <- checkSite(s, u)
		}(s)
	}
	go func() {
		wg.Wait()
		close(results)
	}()

	byCat := map[string][]siteResult{}
	var missing, unknown []string
	hits := 0
	for r := range results {
		switch r.state {
		case stFound:
			hits++
			byCat[r.s.cat] = append(byCat[r.s.cat], r)
		case stMissing:
			missing = append(missing, r.s.name)
		default:
			unknown = append(unknown, r.s.name+"("+r.note+")")
		}
	}

	// Print hits grouped by category, so related accounts sit together.
	catOrder := []struct{ key, label string }{
		{"dev", "Code / developer"}, {"security", "Security"},
		{"social", "Social"}, {"writing", "Writing / blog"},
		{"creative", "Creative / photo"}, {"music", "Music"},
		{"video", "Video"}, {"gaming", "Gaming"},
		{"hobby", "Film / books / hobbies"}, {"commerce", "Creator / commerce"},
	}
	for _, c := range catOrder {
		rs := byCat[c.key]
		if len(rs) == 0 {
			continue
		}
		sort.Slice(rs, func(i, j int) bool { return rs[i].s.name < rs[j].s.name })
		head("%s", c.label)
		for _, r := range rs {
			found("%s: %s", r.s.name, r.url)
			// Gemeinsames Modell: ein belegter Konto-Hinweis, nie eine Identitaet.
			store.Add(Record{Kind: KindAccount, Value: r.url, Title: r.s.name + " (" + u + ")",
				URL: r.url, Evidence: EvIndication, Tags: []string{"username-match"},
				Sources: []Source{{Module: "username", Description: "HTTP check of " + r.s.name,
					URL: r.url, RetrievedAt: nowISO(), Active: true}}})
		}
	}

	sort.Strings(missing)
	sort.Strings(unknown)
	head("Result")
	info("Hits: %d of %d platforms", hits, len(sites))
	if len(missing) > 0 {
		miss("Not taken (%d): %s", len(missing), strings.Join(missing, ", "))
	}
	if len(unknown) > 0 {
		warn("Unclear (%d): %s", len(unknown), strings.Join(unknown, ", "))
	}
}
