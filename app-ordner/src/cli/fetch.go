package main

import (
	"context"
	"crypto/sha1"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// fetchFunc is the single HTTP entry point of all engine modules. Tests
// replace it with recorded fixtures, so no test depends on a live service.
type fetchFunc func(ctx context.Context, url string, hdr map[string]string) (int, []byte, error)

var fetch fetchFunc = liveFetch

// noCache disables the on-disk response cache (tests, --fresh).
var noCache = false

func liveFetch(ctx context.Context, url string, hdr map[string]string) (int, []byte, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return 0, nil, fmt.Errorf("%w: %v", errPermanent, err)
	}
	req.Header.Set("User-Agent", userAgent)
	req.Header.Set("Accept", "*/*")
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	resp, err := client.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	return resp.StatusCode, body, nil
}

// getJSON fetches a URL through the cache and decodes a 200 response.
// 404 is a permanent "nothing there"; 429/5xx are retryable errors.
func getJSON(ctx context.Context, url string, hdr map[string]string, ttl time.Duration, v any) error {
	code, body, err := cachedFetch(ctx, url, hdr, ttl)
	if err != nil {
		return err
	}
	if err := httpErr(code); err != nil {
		return err
	}
	if err := json.Unmarshal(body, v); err != nil {
		return fmt.Errorf("%w: bad JSON from %s", errPermanent, shorten(url, 40))
	}
	return nil
}

func httpErr(code int) error {
	switch {
	case code == 200:
		return nil
	case code == 429 || code >= 500:
		return fmt.Errorf("HTTP %d", code)
	default:
		return fmt.Errorf("%w: HTTP %d", errPermanent, code)
	}
}

type cacheEntry struct {
	Code int       `json:"code"`
	Body []byte    `json:"body"`
	At   time.Time `json:"at"`
}

// cachedFetch serves repeat lookups from disk for ttl, which protects free
// APIs from rate limits and makes re-scans (watch mode) cheap. Only 200 and
// 404 answers are cached; keyed requests are cached by URL only.
func cachedFetch(ctx context.Context, url string, hdr map[string]string, ttl time.Duration) (int, []byte, error) {
	if noCache || ttl <= 0 {
		return fetch(ctx, url, hdr)
	}
	sum := sha1.Sum([]byte(url))
	path := filepath.Join(cacheDir(), hex.EncodeToString(sum[:])+".json")
	if b, err := os.ReadFile(path); err == nil {
		var ce cacheEntry
		if json.Unmarshal(b, &ce) == nil && time.Since(ce.At) < ttl {
			return ce.Code, ce.Body, nil
		}
	}
	code, body, err := fetch(ctx, url, hdr)
	if err == nil && (code == 200 || code == 404) {
		if b, e := json.Marshal(cacheEntry{code, body, time.Now()}); e == nil {
			os.MkdirAll(filepath.Dir(path), 0o700)
			os.WriteFile(path, b, 0o600)
		}
	}
	return code, body, err
}

// ---------------------------------------------------------------------------
// Context-aware DNS over HTTPS for the engine (works in the emulator, which
// has no usable system resolver).
// ---------------------------------------------------------------------------

type dnsResult struct {
	NX      bool // NXDOMAIN: the name does not exist
	Answers []dohAnswer
}

func dohLookup(ctx context.Context, name, rrtype string) (*dnsResult, error) {
	var lastErr error
	for _, ep := range dohEndpoints {
		var rep dohReply
		err := getJSON(ctx, ep+"name="+name+"&type="+rrtype, map[string]string{"Accept": "application/dns-json"}, 30*time.Minute, &rep)
		if err != nil {
			lastErr = err
			continue
		}
		r := &dnsResult{NX: rep.Status == 3}
		want := dnsTypeNum[rrtype]
		for _, a := range rep.Answer {
			if a.Type == want {
				a.Data = strings.TrimSuffix(strings.Trim(a.Data, "\""), ".")
				r.Answers = append(r.Answers, a)
			}
		}
		return r, nil
	}
	return nil, lastErr
}

// dohValues returns just the record data, nil on error.
func dohValues(ctx context.Context, name, rrtype string) []string {
	r, err := dohLookup(ctx, name, rrtype)
	if err != nil {
		return nil
	}
	var out []string
	for _, a := range r.Answers {
		out = append(out, a.Data)
	}
	return out
}
