package main

// geoplaces.go enriches a user-supplied location with REAL, publicly mapped
// businesses and facilities. It uses one bounded Overpass query (not an
// assumed place name from the nearest street address). No household, owner,
// visitor or person tracing. OSM objects remain distinguishable by their IDs.

import (
    "encoding/json"
    "errors"
    "fmt"
    "io"
    "math"
    "net"
    "net/http"
    "net/url"
    "sort"
    "strings"
    "time"
)

const overpassEndpoint = "https://overpass-api.de/api/interpreter"
const nearbyRadiusMeters = 500
const nearbyResultLimit = 28
const nearbyResponseLimit = 2 * 1024 * 1024

type osmPoint struct {
    Lat float64 `json:"lat"`
    Lon float64 `json:"lon"`
}
type osmElement struct {
    Type string            `json:"type"`
    ID int64               `json:"id"`
    Lat float64            `json:"lat"`
    Lon float64            `json:"lon"`
    Center *osmPoint       `json:"center"`
    Tags map[string]string `json:"tags"`
}
type nearbyResponse struct {
    Elements []osmElement `json:"elements"`
}
type nearbyPlace struct {
    ID string
    Name string
    Kind string
    Distance int
    Lat float64
    Lon float64
    Website string
    Phone string
    Email string
    Address string
    Operator string
    SourceURL string
}

func distanceMeters(aLat, aLon, bLat, bLon float64) float64 {
    const rad = math.Pi / 180
    dLat := (bLat-aLat)*rad
    dLon := (bLon-aLon)*rad
    a := math.Sin(dLat/2)*math.Sin(dLat/2) +
         math.Cos(aLat*rad)*math.Cos(bLat*rad)*math.Sin(dLon/2)*math.Sin(dLon/2)
    if a>1 {a=1}
    return 6371000*2*math.Atan2(math.Sqrt(a),math.Sqrt(1-a))
}

// Keep the query bounded. One call obtains clinics, hospitals, restaurants,
// shops and other POIs including node, way and relation representations.
// Unnamed entities are useful: a facility might have healthcare=clinic
// without a name on the map.
func buildNearbyQuery(lat,lon float64, radius int) string {
    if radius<100 {radius=100}
    if radius>1000 {radius=1000}
    at:=fmt.Sprintf("(around:%d,%.6f,%.6f)",radius,lat,lon)
    return "[out:json][timeout:12];(" +
        "nwr"+at+"[amenity~\"^(hospital|clinic|doctors|dentist|pharmacy|restaurant|cafe|fast_food|pub|bar|school|university|library|bank|post_office|townhall|police|fire_station)$\"];" +
        "nwr"+at+"[healthcare];" +
        "nwr"+at+"[tourism~\"^(hotel|guest_house|museum|attraction)$\"];" +
        "nwr"+at+"[shop][name];" +
        "nwr"+at+"[office~\"^(company|government|association)$\"];" +
        ");out center 350;"
}

func cleanField(v string, limit int) string {
    v=strings.TrimSpace(v)
    v=strings.ReplaceAll(v,"\r"," ")
    v=strings.ReplaceAll(v,"\n"," ")
    v=strings.Join(strings.Fields(v)," ")
    if len(v)>limit {v=v[:limit]}
    return v
}

func poiCategory(tags map[string]string) string {
    healthcare:=strings.ToLower(tags["healthcare"])
    a:=strings.ToLower(tags["amenity"])
    switch {
    case healthcare!="",a=="clinic",a=="hospital",a=="doctors",a=="dentist",a=="pharmacy":
        if a=="hospital"||healthcare=="hospital" {return "Hospital"}
        if a=="clinic"||healthcare=="clinic" {return "Clinic"}
        if a=="pharmacy"||healthcare=="pharmacy" {return "Pharmacy"}
        return "Healthcare"
    case a=="restaurant",a=="cafe",a=="fast_food",a=="pub",a=="bar":
        if a=="restaurant" {return "Restaurant"}
        if a=="cafe" {return "Cafe"}
        return "Food & drink"
    case tags["shop"]!="": return "Shop"
    case tags["office"]!="": return "Office"
    case a=="school",a=="university",a=="library": return "Education"
    case tags["tourism"]=="hotel"||tags["tourism"]=="guest_house": return "Hotel"
    case tags["tourism"]=="museum"||tags["tourism"]=="attraction": return "Attraction"
    case a!="": return "Public service"
    default: return "Public place"
    }
}

func isListedPublicFacility(tags map[string]string) bool {
    if tags["healthcare"]!="" {return true}
    switch tags["amenity"] {
    case "hospital","clinic","doctors","dentist","pharmacy","restaurant",
         "cafe","fast_food","pub","bar","school","university","library",
         "bank","post_office","townhall","police","fire_station":
         return true
    }
    switch tags["tourism"] {
    case "hotel","guest_house","museum","attraction": return true
    }
    if tags["shop"]!="" && tags["name"]!="" {return true}
    switch tags["office"] {
    case "company","government","association":return true
    }
    return false
}
func preferOSMTag(t map[string]string, keys ...string) string {
    for _,k:=range keys {
        if v:=cleanField(t[k],160);v!="" {return v}
    }
    return ""
}
func formatPublicAddress(t map[string]string) string {
    street:=strings.TrimSpace(t["addr:street"]+" "+t["addr:housenumber"])
    parts:=[]string{}
    if street!="" {parts=append(parts,street)}
    city:=strings.TrimSpace(t["addr:postcode"]+" "+t["addr:city"])
    if city!="" {parts=append(parts,city)}
    return cleanField(strings.Join(parts,", "),160)
}

// parseNearbyResults is deterministic and testable with fixture data.
// Different OSM IDs with exactly the same name and category at nearly the
// same coordinates often represent a node inside an area; collapse these.
// Do NOT collapse two distinct branches of the same chain across a city.
func parseNearbyResults(raw []byte, lat,lon float64, radius int) ([]nearbyPlace,error) {
    var data nearbyResponse
    if err:=json.Unmarshal(raw,&data);err!=nil{return nil,fmt.Errorf("invalid OSM POI response: %w",err)}
    if len(data.Elements)>500{return nil,errors.New("too many POI features in response")}
    out:=make([]nearbyPlace,0,len(data.Elements))
    seenID:=map[string]bool{}
    for _,e:=range data.Elements {
        if e.ID<=0 || (e.Type!="node"&&e.Type!="way"&&e.Type!="relation") {continue}
        if !isListedPublicFacility(e.Tags) {continue}
        ref:=fmt.Sprintf("%s/%d",e.Type,e.ID)
        if seenID[ref] {continue}
        seenID[ref]=true
        posLat,posLon:=e.Lat,e.Lon
        if e.Center!=nil {posLat,posLon=e.Center.Lat,e.Center.Lon}
        if posLat < -90 || posLat > 90 || posLon < -180 || posLon > 180 {continue}
        dist:=distanceMeters(lat,lon,posLat,posLon)
        // The center of a large mapped hospital polygon can be beyond its
        // boundary's match point, so allow extra room for area features.
        if dist>float64(radius)+300 {continue}
        kind:=poiCategory(e.Tags)
        name:=cleanField(e.Tags["name"],145)
        if name==""{name=cleanField(e.Tags["operator"],145)}
        if name==""{name="Unnamed "+kind}
        p:=nearbyPlace{
            ID:ref,Name:name,Kind:kind,Distance:int(math.Round(dist)),
            Lat:posLat,Lon:posLon,
            Website:preferOSMTag(e.Tags,"contact:website","website","url"),
            Phone:preferOSMTag(e.Tags,"contact:phone","phone"),
            Email:preferOSMTag(e.Tags,"contact:email","email"),
            Address:formatPublicAddress(e.Tags),
            Operator:cleanField(e.Tags["operator"],100),
            SourceURL:"https://www.openstreetmap.org/"+ref,
        }
        // Stable identity is OSM ID. Two overlapping map features with the
        // same name/type and near-identical locations are one practical POI.
        dupe:=-1
        for i:=range out {
            old:=&out[i]
            if old.Kind==p.Kind &&
                strings.EqualFold(old.Name,p.Name) &&
                distanceMeters(old.Lat,old.Lon,p.Lat,p.Lon)<30 {
                dupe=i;break
            }
        }
        if dupe>=0{
            old:=&out[dupe]
            if p.Distance<old.Distance {
                old.Distance=p.Distance
                old.Lat=p.Lat
                old.Lon=p.Lon
            }
            if old.Phone=="" {old.Phone=p.Phone}
            if old.Email=="" {old.Email=p.Email}
            if old.Website=="" {old.Website=p.Website}
            if old.Address=="" {old.Address=p.Address}
            if old.Operator==""{old.Operator=p.Operator}
            continue
        }
        out=append(out,p)
    }
    sort.SliceStable(out,func(i,j int)bool{
        if out[i].Distance!=out[j].Distance {return out[i].Distance<out[j].Distance}
        return out[i].ID<out[j].ID
    })
    if len(out)>nearbyResultLimit {
        // Keep the closest places while reserving space for meaningful
        // facility categories. Otherwise a dense cluster of shops/cafes
        // can hide a clinic even when it is inside the chosen radius.
        chosen:=make([]nearbyPlace,0,nearbyResultLimit)
        included:=map[string]bool{}
        add:=func(p nearbyPlace) {
            if len(chosen)<nearbyResultLimit && !included[p.ID] {
                chosen=append(chosen,p);included[p.ID]=true
            }
        }
        for _,p:=range out {
            if len(chosen)>=14 {break}
            add(p)
        }
        for _,category:=range []string{"Clinic","Hospital","Healthcare","Pharmacy","Restaurant","Cafe","Food & drink","Education","Shop"} {
            added:=0
            for _,p:=range out {
                if p.Kind==category && !included[p.ID] {
                    add(p);added++
                    if added>=2 {break}
                }
            }
        }
        for _,p:=range out {add(p)}
        sort.SliceStable(chosen,func(i,j int)bool{
            return chosen[i].Distance < chosen[j].Distance
        })
        out=chosen
    }
    return out,nil
}

func queryNearbyPlaces(c *http.Client, endpoint string, lat,lon float64,radius int) ([]nearbyPlace,error) {
    if radius<100 || radius>1000 {return nil,errors.New("nearby radius outside supported range")}
    data:=url.Values{"data":{buildNearbyQuery(lat,lon,radius)}}.Encode()
    req,err:=http.NewRequest(http.MethodPost,endpoint,strings.NewReader(data))
    if err!=nil{return nil,err}
    req.Header.Set("Content-Type","application/x-www-form-urlencoded")
    req.Header.Set("Accept","application/json")
    req.Header.Set("User-Agent","FlipperOne-OSINT/1.5 (+https://github.com/wasabicover258/FlipperOne-OSINT)")
    res,err:=c.Do(req)
    if err!=nil{return nil,err}
    defer res.Body.Close()
    if res.StatusCode!=http.StatusOK {
        if res.StatusCode==429{return nil,errors.New("OSM Overpass busy (HTTP 429); try again later")}
        return nil,fmt.Errorf("OSM Overpass HTTP %d",res.StatusCode)
    }
    body,err:=io.ReadAll(io.LimitReader(res.Body,nearbyResponseLimit+1))
    if err!=nil{return nil,err}
    if len(body)>nearbyResponseLimit{return nil,errors.New("OSM place results too large")}
    return parseNearbyResults(body,lat,lon,radius)
}

func likelyPublicBusinessEmail(v string) bool {
    v=strings.TrimSpace(v)
    return len(v)<140 && !strings.ContainsAny(v,"\r\n \t<>") && strings.Count(v,"@")==1
}

func reportNearbyPlace(p nearbyPlace, enrichDomain bool,seen map[string]bool) {
    found("%s: %s (%dm)",p.Kind,p.Name,p.Distance)
    info("Source: %s (OpenStreetMap contributors)",p.SourceURL)
    add:=store.Add(Record{
        Kind:KindPlace,Value:p.ID,Title:p.Name,URL:p.SourceURL,
        Evidence:EvIndication,Tags:[]string{p.Kind},
        Sources:sourced("openstreetmap","Public business/facility listing",p.SourceURL),
    })
    _=add
    if p.Address!=""{
        found("Place address: %s",p.Address)
        info("Source: %s",p.SourceURL)
    }
    if p.Operator!="" && !strings.EqualFold(p.Operator,p.Name){
        info("Public operator: %s",p.Operator)
    }
    if p.Phone!=""{
        found("Business phone: %s",p.Phone)
        info("Source: %s",p.SourceURL)
        store.Add(Record{Kind:KindPhone,Value:p.Phone,Title:"Public business phone",Evidence:EvIndication,Sources:sourced("openstreetmap","Public business contact",p.SourceURL)})
        store.Link(KindPlace,p.ID,"listed phone",KindPhone,p.Phone,EvIndication,p.SourceURL)
    }
    if p.Email!="" && likelyPublicBusinessEmail(p.Email){
        found("Business email: %s",p.Email)
        info("Source: %s",p.SourceURL)
        store.Add(Record{Kind:KindEmail,Value:p.Email,Title:"Public business email",Evidence:EvIndication,Sources:sourced("openstreetmap","Public business contact",p.SourceURL)})
        store.Link(KindPlace,p.ID,"listed email",KindEmail,p.Email,EvIndication,p.SourceURL)
    }
    if p.Website!="" {
        host,err:=normalizeWebInput(p.Website)
        if err==nil{
            link:=p.Website
            if !strings.Contains(link,"://") {link="https://"+link}
            found("Business website: %s",link)
            info("Source: %s",p.SourceURL)
            store.Add(Record{Kind:KindHost,Value:host,Title:"Public business website",Evidence:EvIndication,
                Sources:sourced("openstreetmap","Public business website",p.SourceURL),URL:link})
            store.Link(KindPlace,p.ID,"listed website",KindHost,host,EvIndication,p.SourceURL)
            if enrichDomain && !seen[host]{
                seen[host]=true
                // DNS-only technical pivot; never fetch or scan arbitrary
                // website services. Prevent any private/local IP recording.
                count:=0
                for _,raw:=range ipsOf(host) {
                    ip:=net.ParseIP(raw)
                    if !isPublicIP(ip){continue}
                    found("Public DNS: %s -> %s",host,ip.String())
                    info("Source: public DNS")
                    store.Add(Record{Kind:KindIP,Value:ip.String(),Title:"DNS address for "+host,
                        Evidence:EvIndication,Sources:sourced("dns","DNS for public listed website",p.SourceURL)})
                    store.Link(KindHost,host,"resolves to",KindIP,ip.String(),EvIndication,"DNS")
                    count++
                    if count>=2{break}
                }
            }
        }
    }
}

// Optional exact nameFilter is only used for company/org inputs, so unrelated
// nearby facilities are not presented as matching an organization name.
func showNearbyPlaces(lat,lon float64,radius int,nameFilter string) int {
    head("Nearby facilities and businesses (%dm)",radius)
    info("Source: OpenStreetMap / Overpass; public listings may be incomplete.")
    cli:=&http.Client{Timeout:18*time.Second}
    places,err:=queryNearbyPlaces(cli,overpassEndpoint,lat,lon,radius)
    if err!=nil{
        warn("Nearby search unavailable: %v",err)
        info("Try again later; community Overpass servers can be busy.")
        return 0
    }
    seenDomains:=map[string]bool{}
    n:=0
    query:=strings.ToLower(strings.TrimSpace(nameFilter))
    for _,p:=range places{
        if query!="" && !strings.Contains(strings.ToLower(p.Name),query) &&
            !strings.Contains(query,strings.ToLower(p.Name)){continue}
        }
        if n>=nearbyResultLimit{break}
        n++
        // At most two distinct business websites are DNS-enriched.
        reportNearbyPlace(p,len(seenDomains)<2,seenDomains)
    }
    if n==0{miss("No matching mapped businesses or facilities in this radius")}
    else {found("%d mapped places with public details",n)}
    info("OSM data (c) OpenStreetMap contributors; names and contacts may be outdated.")
    return n
}
