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
	name, url, mode, arg string
}

var sites = []site{
	{"GitHub", "https://github.com/{u}", "status", ""},
	{"GitLab", "https://gitlab.com/api/v4/users?username={u}", "notbody", "[]"},
	{"Codeberg", "https://codeberg.org/{u}", "status", ""},
	{"Bitbucket", "https://bitbucket.org/{u}/", "status", ""},
	{"SourceForge", "https://sourceforge.net/u/{u}/profile", "status", ""},
	{"Launchpad", "https://launchpad.net/~{u}", "status", ""},
	{"HackerNews", "https://hacker-news.firebaseio.com/v0/user/{u}.json", "notbody", "null"},
	{"DEV.to", "https://dev.to/api/users/by_username?url={u}", "status", ""},
	{"DockerHub", "https://hub.docker.com/v2/users/{u}/", "status", ""},
	{"PyPI", "https://pypi.org/user/{u}/", "status", ""},
	{"Keybase", "https://keybase.io/_/api/1.0/user/lookup.json?usernames={u}&fields=basics", "contains", "\"basics\""},
	{"Lichess", "https://lichess.org/api/user/{u}", "status", ""},
	{"Chess.com", "https://api.chess.com/pub/player/{u}", "status", ""},
	{"Codeforces", "https://codeforces.com/api/user.info?handles={u}", "status", "400"},
	{"Mastodon.social", "https://mastodon.social/@{u}", "status", ""},
	{"Bluesky", "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor={u}.bsky.social", "status", "400"},
	{"Gravatar", "https://en.gravatar.com/{u}.json", "status", ""},
	{"Wikipedia(EN)", "https://en.wikipedia.org/w/api.php?action=query&list=users&ususers={u}&format=json", "notcontains", "\"missing\""},
	{"OpenStreetMap", "https://www.openstreetmap.org/user/{u}", "status", ""},
	{"SoundCloud", "https://soundcloud.com/{u}", "status", ""},
	{"Vimeo", "https://vimeo.com/{u}", "status", ""},
	{"Flickr", "https://www.flickr.com/people/{u}/", "status", ""},
	{"Pinterest", "https://www.pinterest.com/{u}/", "status", ""},
	{"Medium", "https://medium.com/@{u}", "status", ""},
	{"YouTube", "https://www.youtube.com/@{u}", "status", ""},
	{"Last.fm", "https://www.last.fm/user/{u}", "status", ""},
	{"Steam", "https://steamcommunity.com/id/{u}", "notcontains", "The specified profile could not be found"},
	{"Itch.io", "https://{u}.itch.io/", "status", ""},
	{"Linktree", "https://linktr.ee/{u}", "status", ""},
	{"About.me", "https://about.me/{u}", "status", ""},
	{"Ko-fi", "https://ko-fi.com/{u}", "status", ""},
	{"Letterboxd", "https://letterboxd.com/{u}/", "status", ""},
	{"Reddit", "https://www.reddit.com/user/{u}/about.json", "status", ""},
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
	case "GitLab":
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
	}
	return strings.ReplaceAll(s.url, "{u}", user)
}

func runUsername(u string) {
	if !validUser.MatchString(u) {
		warn("Invalid username (2-40 characters: a-z 0-9 . _ -)")
		return
	}
	head("Username check: %s", u)
	info("Checking %d public platforms ...", len(sites))
	info("Hit = name is taken there, not necessarily the same person")

	results := make(chan siteResult, len(sites))
	sem := make(chan struct{}, 8)
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

	var missing, unknown []string
	hits := 0
	for r := range results {
		switch r.state {
		case stFound:
			hits++
			found("%s: %s", r.s.name, r.url)
		case stMissing:
			missing = append(missing, r.s.name)
		default:
			unknown = append(unknown, r.s.name+"("+r.note+")")
		}
	}
	sort.Strings(missing)
	sort.Strings(unknown)

	head("Result")
	info("Hits: %d of %d", hits, len(sites))
	if len(missing) > 0 {
		miss("Not taken (%d): %s", len(missing), strings.Join(missing, ", "))
	}
	if len(unknown) > 0 {
		warn("Unclear (%d): %s", len(unknown), strings.Join(unknown, ", "))
	}
}
