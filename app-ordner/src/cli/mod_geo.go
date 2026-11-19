package main

// Places (ported from the 2.0.x GPS/POI code into engine modules):
// place name -> coordinate (Nominatim), coordinate -> nearest address,
// mapped public facilities (OSM Overpass, nearest first), elevation and
// time zone (Open-Meteo), map links and nearby Wikipedia articles.
// Public map features only: no residents, owners, visitors or tracking.

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

var geoRe = regexp.MustCompile(`^\s*(-?\d{1,2}(?:\.\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$`)

// parseGeo accepts "lat,lon" (also "lat lon" / "lat;lon") in decimal degrees.
func parseGeo(s string) (lat, lon float64, ok bool) {
	m := geoRe.FindStringSubmatch(s)
	if m == nil {
		return 0, 0, false
	}
	lat, e1 := strconv.ParseFloat(m[1], 64)
	lon, e2 := strconv.ParseFloat(m[2], 64)
	if e1 != nil || e2 != nil || lat < -90 || lat > 90 || lon < -180 || lon > 180 {
		return 0, 0, false
	}
	return lat, lon, true
}

func geoValue(lat, lon float64) string { return fmt.Sprintf("%.6f,%.6f", lat, lon) }

func fmtCoord(v float64) string { return strconv.FormatFloat(v, 'f', 6, 64) }

func distanceMeters(aLat, aLon, bLat, bLon float64) float64 {
	const rad = math.Pi / 180
	dLat, dLon := (bLat-aLat)*rad, (bLon-aLon)*rad
	a := math.Sin(dLat/2)*math.Sin(dLat/2) + math.Cos(aLat*rad)*math.Cos(bLat*rad)*math.Sin(dLon/2)*math.Sin(dLon/2)
	if a > 1 {
		a = 1
	}
	return 6371000 * 2 * math.Atan2(math.Sqrt(a), math.Sqrt(1-a))
}

// dms formats a coordinate as degrees, minutes, seconds (ASCII "d": the
// device font has no degree sign).
func dms(lat, lon float64) string {
	part := func(v float64, pos, neg string) string {
		h := pos
		if v < 0 {
			h, v = neg, -v
		}
		d := math.Floor(v)
		m := math.Floor((v - d) * 60)
		s := (v - d - m/60) * 3600
		if s >= 59.95 { // avoid 60.0"
			s, m = 0, m+1
		}
		if m >= 60 {
			m, d = 0, d+1
		}
		return fmt.Sprintf("%.0fd%02.0f'%04.1f\"%s", d, m, s, h)
	}
	return part(lat, "N", "S") + " " + part(lon, "E", "W")
}

func geoOf(f Finding) (float64, float64, bool) { return parseGeo(f.Value) }

// ---------------------------------------------------------------------------

var modGeocode = &Module{
	Name: "geocode", Desc: "Place name/address -> coordinate (OSM Nominatim)",
	In: []Kind{KPlace}, Out: []Kind{KGeo, KAttr}, Timeout: 15 * time.Second, Retries: 1, Rate: 1100 * time.Millisecond,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		if len(strings.TrimSpace(in.Value)) < 3 {
			return fmt.Errorf("%w: too short", errPermanent)
		}
		var hits []struct {
			Lat, Lon    string
			DisplayName string `json:"display_name"`
			Category    string `json:"category"`
			Type        string `json:"type"`
		}
		q := url.Values{"q": {in.Value}, "format": {"jsonv2"}, "limit": {"3"}}
		if err := getJSON(ctx, "https://nominatim.openstreetmap.org/search?"+q.Encode(), appUA(), 30*day, &hits); err != nil {
			return err
		}
		for i, h := range hits {
			lat, e1 := strconv.ParseFloat(h.Lat, 64)
			lon, e2 := strconv.ParseFloat(h.Lon, 64)
			if e1 != nil || e2 != nil {
				continue
			}
			if i == 0 { // best match is followed (POIs, elevation ...)
				out.Add(Finding{Type: KGeo, Value: geoValue(lat, lon), Source: "nominatim", Confidence: 70,
					Detail: shorten(h.DisplayName, 100), Data: map[string]string{"osm": h.Category + "/" + h.Type}})
				continue
			}
			out.Add(Finding{Type: KAttr, Value: "Other match: " + shorten(h.DisplayName, 80) + " @ " + geoValue(lat, lon),
				Source: "nominatim", Confidence: 40})
		}
		return nil
	},
}

var modGeoLinks = &Module{
	Name: "maplinks", Desc: "Coordinate -> map links and DMS notation (offline)",
	In: []Kind{KGeo}, Out: []Kind{KURL, KAttr},
	Run: func(ctx context.Context, in Finding, out *Out) error {
		lat, lon, ok := geoOf(in)
		if !ok {
			return fmt.Errorf("%w: bad coordinate", errPermanent)
		}
		la, lo := fmtCoord(lat), fmtCoord(lon)
		out.Add(Finding{Type: KAttr, Value: "DMS: " + dms(lat, lon), Source: "offline", Confidence: 100})
		for _, l := range []struct{ u, d string }{
			{"https://www.openstreetmap.org/?mlat=" + la + "&mlon=" + lo + "#map=17/" + la + "/" + lo, "OpenStreetMap"},
			{"https://www.google.com/maps/search/?api=1&query=" + la + "%2C" + lo, "Google Maps"},
			{"https://www.bing.com/maps?cp=" + la + "~" + lo + "&lvl=17", "Bing Maps"},
			{"geo:" + la + "," + lo, "geo URI (opens the device map app)"},
		} {
			out.Add(Finding{Type: KURL, Value: l.u, Source: "offline", Confidence: 100, Detail: l.d})
		}
		return nil
	},
}

var modGeoMeta = &Module{
	Name: "geo-meta", Desc: "Coordinate -> elevation, time zone, UTC offset (Open-Meteo)",
	In: []Kind{KGeo}, Out: []Kind{KAttr}, Timeout: 15 * time.Second, Retries: 1,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		lat, lon, ok := geoOf(in)
		if !ok {
			return fmt.Errorf("%w: bad coordinate", errPermanent)
		}
		var r struct {
			Elevation *float64 `json:"elevation"`
			Timezone  string   `json:"timezone"`
			Abbrev    string   `json:"timezone_abbreviation"`
			Offset    int      `json:"utc_offset_seconds"`
		}
		u := "https://api.open-meteo.com/v1/forecast?latitude=" + fmtCoord(lat) + "&longitude=" + fmtCoord(lon) + "&timezone=auto&forecast_days=1"
		if err := getJSON(ctx, u, nil, 30*day, &r); err != nil {
			return err
		}
		if r.Elevation != nil {
			out.Add(Finding{Type: KAttr, Value: fmt.Sprintf("Elevation: %.0f m", *r.Elevation), Source: "open-meteo", Confidence: 85,
				Detail: "terrain model (90 m grid)"})
		}
		if r.Timezone != "" {
			sign, off := "+", r.Offset
			if off < 0 {
				sign, off = "-", -off
			}
			d := fmt.Sprintf("UTC%s%02d:%02d", sign, off/3600, off%3600/60)
			if r.Abbrev != "" {
				d += " (" + r.Abbrev + ")"
			}
			out.Add(Finding{Type: KAttr, Value: "Time zone: " + r.Timezone, Source: "open-meteo", Confidence: 95, Detail: d})
		}
		return nil
	},
}

var modReverseGeo = &Module{
	Name: "reverse-geo", Desc: "Coordinate -> nearest mapped address (OSM Nominatim)",
	In: []Kind{KGeo}, Out: []Kind{KAttr}, Timeout: 15 * time.Second, Retries: 1, Rate: 1100 * time.Millisecond,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		lat, lon, ok := geoOf(in)
		if !ok {
			return fmt.Errorf("%w: bad coordinate", errPermanent)
		}
		var r struct {
			DisplayName string `json:"display_name"`
			Category    string `json:"category"`
			Type        string `json:"type"`
			Address     struct {
				CountryCode string `json:"country_code"`
			} `json:"address"`
		}
		u := "https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=18&lat=" + fmtCoord(lat) + "&lon=" + fmtCoord(lon)
		if err := getJSON(ctx, u, appUA(), 30*day, &r); err != nil {
			return err
		}
		if r.DisplayName != "" {
			out.Add(Finding{Type: KAttr, Value: "Nearest address: " + shorten(r.DisplayName, 110), Source: "nominatim", Confidence: 75,
				Detail: "closest mapped feature " + r.Category + "/" + r.Type, Data: map[string]string{"country": strings.ToUpper(r.Address.CountryCode)}})
		}
		return nil
	},
}

// ---------------------------------------------------------------------------
// Overpass: public facilities around a coordinate, strictly nearest first.
// ---------------------------------------------------------------------------

// Two independent community servers; the second is only asked if the
// first fails.
var overpassEndpoints = []string{"https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter"}

const (
	poiRadius = 500
	poiLimit  = 28
)

func buildNearbyQuery(lat, lon float64, radius int) string {
	if radius < 100 {
		radius = 100
	}
	if radius > 1000 {
		radius = 1000
	}
	at := fmt.Sprintf("(around:%d,%.6f,%.6f)", radius, lat, lon)
	return "[out:json][timeout:12];(" +
		"nwr" + at + `[amenity~"^(hospital|clinic|doctors|dentist|pharmacy|restaurant|cafe|fast_food|pub|bar|school|university|library|bank|post_office|townhall|police|fire_station)$"];` +
		"nwr" + at + "[healthcare];" +
		"nwr" + at + `[tourism~"^(hotel|guest_house|museum|attraction)$"];` +
		"nwr" + at + "[shop][name];" +
		"nwr" + at + `[office~"^(company|government|association)$"];` +
		");out center 350;"
}

type osmElement struct {
	Type   string  `json:"type"`
	ID     int64   `json:"id"`
	Lat    float64 `json:"lat"`
	Lon    float64 `json:"lon"`
	Center *struct {
		Lat float64 `json:"lat"`
		Lon float64 `json:"lon"`
	} `json:"center"`
	Tags map[string]string `json:"tags"`
}

type nearbyPlace struct {
	Ref, Name, Kind                          string
	Distance                                 int
	Lat, Lon                                 float64
	Website, Phone, Email, Address, Operator string
}

func cleanField(v string, limit int) string {
	v = strings.Join(strings.Fields(v), " ")
	if len(v) > limit {
		v = v[:limit]
	}
	return v
}

func poiCategory(t map[string]string) string {
	hc, a := strings.ToLower(t["healthcare"]), strings.ToLower(t["amenity"])
	switch {
	case a == "hospital" || hc == "hospital":
		return "Hospital"
	case a == "clinic" || hc == "clinic":
		return "Clinic"
	case a == "pharmacy" || hc == "pharmacy":
		return "Pharmacy"
	case hc != "" || a == "doctors" || a == "dentist":
		return "Healthcare"
	case a == "restaurant":
		return "Restaurant"
	case a == "cafe":
		return "Cafe"
	case a == "fast_food" || a == "pub" || a == "bar":
		return "Food & drink"
	case t["shop"] != "":
		return "Shop"
	case t["office"] != "":
		return "Office"
	case a == "school" || a == "university" || a == "library":
		return "Education"
	case t["tourism"] == "hotel" || t["tourism"] == "guest_house":
		return "Hotel"
	case t["tourism"] != "":
		return "Attraction"
	case a != "":
		return "Public service"
	}
	return "Public place"
}

// isListedPublicFacility keeps the result to the queried facility classes
// (never private houses or unnamed shops).
func isListedPublicFacility(t map[string]string) bool {
	if t["healthcare"] != "" {
		return true
	}
	switch t["amenity"] {
	case "hospital", "clinic", "doctors", "dentist", "pharmacy", "restaurant", "cafe", "fast_food", "pub", "bar",
		"school", "university", "library", "bank", "post_office", "townhall", "police", "fire_station":
		return true
	}
	switch t["tourism"] {
	case "hotel", "guest_house", "museum", "attraction":
		return true
	}
	switch t["office"] {
	case "company", "government", "association":
		return true
	}
	return t["shop"] != "" && t["name"] != ""
}

func firstTag(t map[string]string, keys ...string) string {
	for _, k := range keys {
		if v := cleanField(t[k], 160); v != "" {
			return v
		}
	}
	return ""
}

// parseNearby is deterministic: nearest first, ties by OSM ID; overlapping
// representations of one facility (node inside its building way) collapse.
func parseNearby(raw []byte, lat, lon float64, radius int) ([]nearbyPlace, error) {
	var data struct {
		Elements []osmElement `json:"elements"`
	}
	if err := json.Unmarshal(raw, &data); err != nil {
		return nil, fmt.Errorf("%w: invalid Overpass response", errPermanent)
	}
	if len(data.Elements) > 1000 {
		return nil, errors.New("too many POIs in response")
	}
	var out []nearbyPlace
	seen := map[string]bool{}
	for _, e := range data.Elements {
		if e.ID <= 0 || (e.Type != "node" && e.Type != "way" && e.Type != "relation") || !isListedPublicFacility(e.Tags) {
			continue
		}
		ref := fmt.Sprintf("%s/%d", e.Type, e.ID)
		if seen[ref] {
			continue
		}
		seen[ref] = true
		pl, po := e.Lat, e.Lon
		if e.Center != nil {
			pl, po = e.Center.Lat, e.Center.Lon
		}
		dist := distanceMeters(lat, lon, pl, po)
		if dist > float64(radius)+300 { // area centres can lie beyond the radius
			continue
		}
		kind := poiCategory(e.Tags)
		name := cleanField(e.Tags["name"], 100)
		if name == "" {
			name = cleanField(e.Tags["operator"], 100)
		}
		if name == "" {
			name = "Unnamed " + strings.ToLower(kind)
		}
		addr := cleanField(strings.Join(filterEmpty(strings.TrimSpace(e.Tags["addr:street"]+" "+e.Tags["addr:housenumber"]),
			strings.TrimSpace(e.Tags["addr:postcode"]+" "+e.Tags["addr:city"])), ", "), 120)
		p := nearbyPlace{Ref: ref, Name: name, Kind: kind, Distance: int(math.Round(dist)), Lat: pl, Lon: po,
			Website: firstTag(e.Tags, "contact:website", "website", "url"), Phone: firstTag(e.Tags, "contact:phone", "phone"),
			Email: firstTag(e.Tags, "contact:email", "email"), Address: addr, Operator: cleanField(e.Tags["operator"], 80)}
		dup := -1
		for i := range out {
			if out[i].Kind == p.Kind && strings.EqualFold(out[i].Name, p.Name) && distanceMeters(out[i].Lat, out[i].Lon, p.Lat, p.Lon) < 30 {
				dup = i
				break
			}
		}
		if dup < 0 {
			out = append(out, p)
			continue
		}
		o := &out[dup]
		if p.Distance < o.Distance {
			o.Distance, o.Lat, o.Lon = p.Distance, p.Lat, p.Lon
		}
		for _, f := range []struct {
			dst *string
			src string
		}{{&o.Website, p.Website}, {&o.Phone, p.Phone}, {&o.Email, p.Email},
			{&o.Address, p.Address}, {&o.Operator, p.Operator}} {
			if *f.dst == "" {
				*f.dst = f.src
			}
		}
	}
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].Distance != out[j].Distance {
			return out[i].Distance < out[j].Distance
		}
		return out[i].Ref < out[j].Ref
	})
	if len(out) > poiLimit {
		out = out[:poiLimit]
	}
	return out, nil
}

var modOverpass = &Module{
	Name: "overpass", Desc: "Coordinate -> nearby public facilities + contacts (OSM Overpass)",
	In: []Kind{KGeo}, Out: []Kind{KPlace, KDomain}, Timeout: 25 * time.Second, Retries: 1, Rate: 2 * time.Second,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		lat, lon, ok := geoOf(in)
		if !ok {
			return fmt.Errorf("%w: bad coordinate", errPermanent)
		}
		q := url.QueryEscape(buildNearbyQuery(lat, lon, poiRadius))
		var places []nearbyPlace
		var err error
		for _, ep := range overpassEndpoints {
			var code int
			var body []byte
			code, body, err = cachedFetch(ctx, ep+"?data="+q, appUA(), day)
			if err == nil {
				err = httpErr(code)
			}
			if err == nil {
				if places, err = parseNearby(body, lat, lon, poiRadius); err == nil {
					break
				}
			}
			if ctx.Err() != nil {
				return ctx.Err()
			}
		}
		if err != nil {
			return err
		}
		for _, p := range places {
			d := fmt.Sprintf("%s, %d m", p.Kind, p.Distance)
			for _, x := range []string{p.Address, p.Phone, p.Email} {
				if x != "" && !strings.ContainsAny(x, "<>") {
					d += "; " + x
				}
			}
			data := map[string]string{"osm": "https://www.openstreetmap.org/" + p.Ref, "kind": p.Kind,
				"distance_m": strconv.Itoa(p.Distance), "lat": fmtCoord(p.Lat), "lon": fmtCoord(p.Lon)}
			for k, v := range map[string]string{"website": p.Website, "phone": p.Phone, "email": p.Email, "address": p.Address, "operator": p.Operator} {
				if v != "" {
					data[k] = v
				}
			}
			out.Add(Finding{Type: KPlace, Value: p.Name + " (" + p.Ref + ")", Source: "overpass", Confidence: 85, Detail: d, Data: data})
			if p.Website != "" {
				if dom, ok := websiteDomain(p.Website); ok {
					out.Add(Finding{Type: KDomain, Value: dom, Source: "overpass", Confidence: 60,
						Detail: "listed website of " + p.Name, Data: map[string]string{"relation": "listed website", "url": p.Website}})
				}
			}
		}
		return nil
	},
}

var modWikiGeo = &Module{
	Name: "wiki-geo", Desc: "Coordinate -> nearby Wikipedia articles (1 km)",
	In: []Kind{KGeo}, Out: []Kind{KURL}, Timeout: 15 * time.Second, Retries: 1,
	Run: func(ctx context.Context, in Finding, out *Out) error {
		lat, lon, ok := geoOf(in)
		if !ok {
			return fmt.Errorf("%w: bad coordinate", errPermanent)
		}
		var g struct {
			Query struct {
				GeoSearch []struct {
					PageID int64   `json:"pageid"`
					Title  string  `json:"title"`
					Dist   float64 `json:"dist"`
				} `json:"geosearch"`
			} `json:"query"`
		}
		q := url.Values{"action": {"query"}, "list": {"geosearch"}, "gscoord": {fmtCoord(lat) + "|" + fmtCoord(lon)},
			"gsradius": {"1000"}, "gslimit": {"5"}, "format": {"json"}}
		if err := getJSON(ctx, "https://en.wikipedia.org/w/api.php?"+q.Encode(), appUA(), 30*day, &g); err != nil {
			return err
		}
		for _, p := range g.Query.GeoSearch {
			if p.PageID > 0 && p.Dist <= 1000 {
				out.Add(Finding{Type: KURL, Value: "https://en.wikipedia.org/?curid=" + strconv.FormatInt(p.PageID, 10), Source: "wikipedia",
					Confidence: 60, Detail: fmt.Sprintf("%s (%.0f m)", p.Title, p.Dist)})
			}
		}
		return nil
	},
}
