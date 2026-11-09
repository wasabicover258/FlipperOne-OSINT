package main

// multirecon.go: small, opt-in public-data pivots for technical objects,
// organisations, places, and vehicle specifications. No owner tracing.
// Every relation has a source. There is no unbounded recursion.

import (
    "encoding/json"
    "errors"
    "fmt"
    "io"
    "net"
    "net/http"
    "net/url"
    "regexp"
    "strconv"
    "strings"
    "unicode"
)

var vinRE = regexp.MustCompile(`^[A-HJ-NPR-Z0-9]{17}$`)
var asnRE = regexp.MustCompile(`^(?:AS)?([0-9]{1,10})$`)
var ethRE = regexp.MustCompile(`^0x[0-9a-fA-F]{40}$`)
var btcRE = regexp.MustCompile(`^(?:bc1[ac-hj-np-z02-9]{11,87}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$`)

func sourced(module, desc, link string) []Source {
    return []Source{{Module:module, Description:desc, URL:link, RetrievedAt:nowISO(), ToolVersion:"public API", Active:false}}
}

func addOne(kind, val, title, sourceName, sourceURL string) *Record {
    return store.Add(Record{Kind:kind, Value:val, Title:title, Evidence:EvIndication,
        Sources:sourced(sourceName,sourceName,sourceURL), URL:sourceURL})
}

func normalizeWebInput(raw string) (string, error) {
    raw=strings.TrimSpace(raw)
    if raw=="" {return "",errors.New("empty website")}
    if !strings.Contains(raw,"://") {raw="https://"+raw}
    u,err:=url.Parse(raw)
    if err!=nil || (u.Scheme!="http"&&u.Scheme!="https") || u.User!=nil {
        return "",errors.New("use an HTTP(S) URL or domain")}
    host:=strings.ToLower(strings.TrimSuffix(u.Hostname(),"."))
    if host==""||strings.ContainsAny(host," \t\r\n")||strings.HasSuffix(host,".local")||host=="localhost" {
        return "",errors.New("invalid public hostname")}
    if net.ParseIP(host)!=nil {return "",errors.New("IP address: use IPv4 / IPv6 mode")}
    if !domainRe.MatchString(host) {return "",errors.New("invalid domain")}
    return host,nil
}

func runWebInput(raw string) {
    host,err:=normalizeWebInput(raw)
    if err!=nil {warn("Domain / URL: %v",err);return}
    head("Website / domain: %s",host)
    runDomain(host)
}

func runTypedIP(raw string, wantV6 bool) {
    val:=net.ParseIP(strings.TrimSpace(raw))
    if val==nil {warn("Invalid IP address");return}
    if wantV6 && val.To4()!=nil {warn("Expected IPv6, got IPv4");return}
    if !wantV6 && val.To4()==nil {warn("Expected IPv4, got IPv6");return}
    runIP(val.String())
}

type osmHit struct {
    PlaceID int64 `json:"place_id"`
    Name string `json:"name"`
    DisplayName string `json:"display_name"`
    Lat string `json:"lat"`
    Lon string `json:"lon"`
    Type string `json:"type"`
    Category string `json:"category"`
}

func parseGPS(value string) (float64,float64,error) {
    parts:=strings.Split(value,",")
    if len(parts)!=2 {return 0,0,errors.New("format: latitude, longitude")}
    lat,e1:=strconv.ParseFloat(strings.TrimSpace(parts[0]),64)
    lon,e2:=strconv.ParseFloat(strings.TrimSpace(parts[1]),64)
    if e1!=nil||e2!=nil||lat < -90||lat > 90||lon < -180||lon > 180 {
        return 0,0,errors.New("latitude -90..90, longitude -180..180")}
    return lat,lon,nil
}

func osmRequest(endpoint string, values url.Values, out any) error {
    u,err:=url.Parse(endpoint)
    if err!=nil{return err}
    u.RawQuery=values.Encode()
    req,err:=http.NewRequest(http.MethodGet,u.String(),nil)
    if err!=nil{return err}
    // Nominatim's published usage policy requires an identifiable application
    // User-Agent rather than a generic browser string.
    req.Header.Set("User-Agent","FlipperOne-OSINT/1.3 (https://github.com/wasabicover258/FlipperOne-OSINT; issue tracker)")
    req.Header.Set("Accept","application/json")
    resp,err:=client.Do(req)
    if err!=nil{return err}
    defer resp.Body.Close()
    if resp.StatusCode!=http.StatusOK{return fmt.Errorf("OpenStreetMap HTTP %d",resp.StatusCode)}
    body,err:=io.ReadAll(io.LimitReader(resp.Body,512*1024+1))
    if err!=nil{return err}
    if len(body)>512*1024{return errors.New("OpenStreetMap response exceeds limit")}
    return json.Unmarshal(body,out)
}

func runGPS(input string) {
    lat,lon,err:=parseGPS(input)
    if err!=nil {warn("GPS: %v",err);return}
    position:=fmt.Sprintf("%.6f, %.6f",lat,lon)
    head("Coordinates: %s",position)
    osmURL:=fmt.Sprintf("https://www.openstreetmap.org/?mlat=%.6f&mlon=%.6f#map=16/%.6f/%.6f",lat,lon,lat,lon)
    found("Map: %s",osmURL)
    addOne(KindMeta,position,"Geographic coordinate","input",osmURL)
    var hit osmHit
    q:=url.Values{"format":{"jsonv2"},"lat":{strconv.FormatFloat(lat,'f',6,64)},
      "lon":{strconv.FormatFloat(lon,'f',6,64)},"zoom":{"14"},"addressdetails":{"0"}}
    if err:=osmRequest("https://nominatim.openstreetmap.org/reverse",q,&hit);err!=nil {
      warn("OSM reverse-geocoding unavailable: %v",err);return
    }
    if hit.DisplayName!="" {
      found("Public map label: %s",shorten(hit.DisplayName,140))
      info("OSM category: %s / %s",hit.Category,hit.Type)
      info("Source: OpenStreetMap contributors (Nominatim)")
      // No occupants, household members, home ownership or contact lookup.
    }
}

func runAddress(input string) {
    if len(strings.TrimSpace(input))<4 {warn("Enter an address or public place name");return}
    head("Geographic lookup")
    info("Public map features only: no residents or property-owner lookup.")
    q:=url.Values{"q":{input},"format":{"jsonv2"},"limit":{"3"},"addressdetails":{"0"}}
    var hits []osmHit
    if err:=osmRequest("https://nominatim.openstreetmap.org/search",q,&hits);err!=nil {
      warn("OSM geocoding unavailable: %v",err);return
    }
    if len(hits)==0 {miss("No public map match found");return}
    for _,h:=range hits {
      lat,errLat:=strconv.ParseFloat(h.Lat,64)
      lon,errLon:=strconv.ParseFloat(h.Lon,64)
      if errLat!=nil||errLon!=nil {continue}
      label:=fmt.Sprintf("%.6f, %.6f",lat,lon)
      found("%s",shorten(h.DisplayName,130))
      info("Coordinates: %s | %s/%s",label,h.Category,h.Type)
      src:=fmt.Sprintf("https://www.openstreetmap.org/?mlat=%.6f&mlon=%.6f",lat,lon)
      info("Source: %s",src)
      addOne(KindMeta,label,"Public OSM feature","openstreetmap",src)
    }
}

func entityClaimIDs(ent wikiClaimMap, prop string) []string {
    var out []string
    for _,c:=range ent[prop] {
      var v struct{ ID string `json:"id"` }
      if json.Unmarshal(c.Mainsnak.Datavalue.Value,&v)==nil && entityID.MatchString(v.ID) {
         out=append(out,v.ID)
      }
    }
    return uniq(out)
}

// Same layout as Wikidata's claims, using a reusable named type.
type wikiClaimMap map[string][]struct{
 Mainsnak struct{Datavalue struct{Value json.RawMessage `json:"value"`} `json:"datavalue"`} `json:"mainsnak"`
}

type orgEntities struct{
 Entities map[string]struct{Claims wikiClaimMap `json:"claims"`} `json:"entities"`
}

func entityStrings(c wikiClaimMap, prop string) []string {
    var a []string
    for _,item:=range c[prop] {
        var s string
        if json.Unmarshal(item.Mainsnak.Datavalue.Value,&s)==nil && s!="" {
            a=append(a,s)
        }
    }
    return uniq(a)
}

func runOrganization(query string) {
    // A bounded one-pass pipeline: candidate -> official website -> public IP -> ASN.
    seen := map[string]bool{}
    query=strings.TrimSpace(query)
    if len(query)<2 {warn("Enter an organization or company name");return}
    head("Organization / company")
    info("Wikidata + OpenStreetMap. Matches are candidates, not legal verification.")
    var search wikiSearch
    q:=url.Values{"action":{"wbsearchentities"},"search":{query},"language":{"en"},
      "format":{"json"},"type":{"item"},"limit":{"4"}}
    if err:=wikiFetch(client,wikidataAPI,q,&search);err!=nil {
      warn("Wikidata unavailable: %v",err)
    } else {
      var ids []string
      for _,it:=range search.Search {if entityID.MatchString(it.ID){ids=append(ids,it.ID)}}
      var details orgEntities
      if len(ids)>0 {
         q=url.Values{"action":{"wbgetentities"},"ids":{strings.Join(ids,"|")},
             "props":{"claims"},"format":{"json"}}
         if err:=wikiFetch(client,wikidataAPI,q,&details);err!=nil {
             warn("Wikidata claims unavailable: %v",err)
         }
      }
      for _,it:=range search.Search {
        if !entityID.MatchString(it.ID) {continue}
        link:="https://www.wikidata.org/wiki/"+it.ID
        found("%s (%s) - %s",it.Label,it.ID,shorten(it.Description,75))
        info("Source: %s",link)
        if it.Label!=""{addOne(KindOrg,it.Label,it.Description,"wikidata",link)}
        claims:=details.Entities[it.ID].Claims
        for _,rawURL:=range entityStrings(claims,"P856") {
          host,err:=normalizeWebInput(rawURL)
          if err!=nil {continue}
          found("Official website: %s",rawURL)
          info("Hostname: %s",host)
          // Bounded technical pivot: only DNS resolution of a documented official website.
          // Never automatically port-scan the derived address or visit a private endpoint.
          resolveOrgDomain(it.Label,host,link,seen)
        }
        for _,p:=range []struct{prop,label string}{
            {"P749","Parent entity"},{"P355","Subsidiary"},{"P159","Headquarters"},
        }{
          for _,qid:=range entityClaimIDs(claims,p.prop) {
            info("%s: https://www.wikidata.org/wiki/%s",p.label,qid)
          }
        }
      }
      if len(search.Search)==0 {miss("No matching Wikidata entry")}
    }
    // Second, independent public-source route: business/place records in OSM.
    var osm []osmHit
    if err:=osmRequest("https://nominatim.openstreetmap.org/search",
      url.Values{"q":{query},"format":{"jsonv2"},"limit":{"2"},"addressdetails":{"0"}},&osm);err==nil {
        for _,place:=range osm {
           if place.Name!=""{found("OSM place candidate: %s",place.Name)}
           info("OSM: %s (%s)",shorten(place.DisplayName,110),place.Type)
           if place.Name!="" {addOne(KindOrg,place.Name,"OSM place candidate","openstreetmap",
             "https://www.openstreetmap.org/search?query="+url.QueryEscape(place.Name))}
        }
    } else {warn("OSM organization search unavailable: %v",err)}
}

func isPublicIP(ip net.IP) bool {
   return ip!=nil && ip.IsGlobalUnicast() && !ip.IsPrivate() && !ip.IsLoopback() &&
     !ip.IsLinkLocalUnicast() && !ip.IsLinkLocalMulticast()
}
/* resolveOrgDomain performs a depth-limited technical pivot from Wikidata
 * organizational metadata. It never scans newly discovered IPs, and never
 * follows an identity/employee chain. Public network-only data is requested. */
func resolveOrgDomain(org, host, link string, seen map[string]bool) {
    if !strings.Contains(host, ".") || strings.HasSuffix(host, ".local") { return }
    addOne(KindHost, host, "Publicly listed official website", "wikidata", link)
    store.Link(KindOrg, org, "official website", KindHost, host, EvIndication, link)
    if seen[host] || len(seen) >= 4 { return }
    seen[host] = true
    ips := ipsOf(host)
    n := 0
    for _, raw := range ips {
        ip := net.ParseIP(raw)
        if !isPublicIP(ip) { continue }
        if n >= 3 { break }
        n++
        addOne(KindIP, ip.String(), "Public DNS answer for " + host, "dns", link)
        store.Link(KindHost, host, "DNS resolves to", KindIP, ip.String(), EvIndication, "DNS")
        found("DNS: %s -> %s", host, ip.String())

        // Only the first two addresses per host receive a RIPEstat ASN lookup,
        // to keep the app usable on a small ARM64 device.
        if n > 2 { continue }
        endpoint := "https://stat.ripe.net/data/network-info/data.json?resource=" + url.QueryEscape(ip.String())
        var nw struct {
            Data struct {
                Asns []int  `json:"asns"`
                Prefix string `json:"prefix"`
            } `json:"data"`
        }
        resp, body, err := get(client, endpoint)
        if err != nil || resp.StatusCode != http.StatusOK || json.Unmarshal(body, &nw) != nil { continue }
        for j, as := range nw.Data.Asns {
            if j >= 2 || as <= 0 { break }
            asn := fmt.Sprintf("AS%d", as)
            addOne(KindMeta, asn, "Public routing ASN", "ripestat", endpoint)
            store.Link(KindIP, ip.String(), "routed via", KindMeta, asn, EvIndication, endpoint)
            found("Network: %s -> %s", ip.String(), asn)
        }
    }
}

func runRegistry(reg string) {
    reg=strings.TrimSpace(reg)
    if len(reg)<3||len(reg)>70{warn("Invalid registration identifier");return}
    head("Company registration identifier")
    found("Entered registry ID: %s",reg)
    info("Registry country/jurisdiction must be verified separately.")
    info("German registry portal: https://www.handelsregister.de/")
    info("UK Companies House: https://find-and-update.company-information.service.gov.uk/")
    info("No register owner, officer or financial data asserted without a matching record.")
}

func vinCheckDigit(v string) bool {
    if !vinRE.MatchString(v){return false}
    values:=map[byte]int{
      'A':1,'B':2,'C':3,'D':4,'E':5,'F':6,'G':7,'H':8,'J':1,'K':2,'L':3,
      'M':4,'N':5,'P':7,'R':9,'S':2,'T':3,'U':4,'V':5,'W':6,'X':7,'Y':8,'Z':9,
    }
    weights:=[17]int{8,7,6,5,4,3,2,10,0,9,8,7,6,5,4,3,2}
    sum:=0
    for i:=0;i<17;i++{c:=v[i];value:=0;if c>='0'&&c<='9'{value=int(c-'0')}else{value=values[c]};sum+=value*weights[i]}
    r:=sum%11
    expect:=byte('0'+r)
    if r==10{expect='X'}
    return v[8]==expect
}

func runVIN(input string) {
    v:=strings.ToUpper(strings.TrimSpace(input))
    head("Vehicle identification number")
    if !vinRE.MatchString(v){warn("VIN must contain 17 characters (no I, O, Q)");return}
    found("VIN format valid: %s",v)
    if vinCheckDigit(v){found("VIN check digit: valid (North American algorithm)")}else{
      info("VIN check digit not confirmed (regional rules can differ)")
    }
    // NHTSA vPIC returns manufacturer/model information only, not ownership.
    u:="https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/"+url.PathEscape(v)+"?format=json"
    type vpicResp struct{Results []map[string]string `json:"Results"`}
    var out vpicResp
    res,body,err:=get(client,u)
    if err!=nil{warn("NHTSA lookup unavailable: %v",err);return}
    if res.StatusCode!=http.StatusOK||json.Unmarshal(body,&out)!=nil||len(out.Results)==0{
      warn("NHTSA vehicle details unavailable");return
    }
    for _,p:=range []struct{key,label string}{
      {"Make","Manufacturer / brand"},{"Model","Model"},{"ModelYear","Model year"},
      {"VehicleType","Vehicle type"},{"PlantCountry","Manufacturing country"},
    }{
      value:=strings.TrimSpace(out.Results[0][p.key])
      if value!=""&&value!="Not Applicable"{found("%s: %s",p.label,value)}
    }
    info("Source: NHTSA vPIC; no owner/registration lookup.")
}

func runPlate(input string) {
    v:=strings.ToUpper(strings.TrimSpace(input))
    if len(v)<2||len(v)>16{warn("Enter a vehicle plate (2-16 chars)");return}
    for _,r:=range v{
       if !(unicode.IsLetter(r)||unicode.IsDigit(r)||r=='-'||r==' '){warn("Invalid plate characters");return}
    }
    head("Vehicle plate")
    found("Normalized plate: %s",v)
    info("Choose a country and consult its official public registers, if permitted.")
    info("No owner, residence, location tracking or automatic plate-to-person search.")
}

func runWallet(raw string) {
    w:=strings.TrimSpace(raw)
    head("Crypto wallet / address")
    var network,explorer string
    switch{
    case ethRE.MatchString(w):
       network="EVM format (Ethereum and compatible chains)"
       explorer="https://etherscan.io/address/"+w
    case btcRE.MatchString(w):
       network="Bitcoin-compatible format (not verified checksum)"
       explorer="https://www.blockchain.com/explorer/addresses/btc/"+url.PathEscape(w)
    default:
       warn("Unknown or unsupported address format");return
    }
    found("Possible network: %s",network)
    info("Public explorer: %s",explorer)
    info("An address is not proof of the wallet owner's identity.")
    addOne(KindMeta,strings.ToLower(w),"Public blockchain address","input",explorer)
}

func runASN(input string) {
    a:=strings.ToUpper(strings.TrimSpace(input))
    m:=asnRE.FindStringSubmatch(a)
    if m==nil{warn("ASN format: AS12345");return}
    n,err:=strconv.ParseUint(m[1],10,32)
    if err!=nil||n==0||n>4294967295{warn("Invalid ASN");return}
    asn:=fmt.Sprintf("AS%d",n)
    head("Autonomous system %s",asn)
    src:="https://stat.ripe.net/AS"+strconv.FormatUint(n,10)
    info("RIPEstat: %s",src)
    u:="https://stat.ripe.net/data/as-overview/data.json?resource="+asn
    var o struct{Data struct{
      Holder string `json:"holder"`
      Resource string `json:"resource"`
    } `json:"data"`}
    r,body,err:=get(client,u)
    if err!=nil||r.StatusCode!=http.StatusOK||json.Unmarshal(body,&o)!=nil {
        warn("RIPEstat ASN overview unavailable");return
    }
    if o.Data.Holder!=""{
       found("Public AS holder: %s",o.Data.Holder)
       addOne(KindOrg,o.Data.Holder,"RIPEstat ASN holder","ripestat",u)
    }
    // Bounded second query for announced prefixes.
    prefixes:="https://stat.ripe.net/data/announced-prefixes/data.json?resource="+asn
    var prefixData struct{Data struct{Prefixes []struct{Prefix string `json:"prefix"`} `json:"prefixes"`} `json:"data"`}
    r,body,err=get(client,prefixes)
    if err!=nil||r.StatusCode!=http.StatusOK||json.Unmarshal(body,&prefixData)!=nil{return}
    for i,p:=range prefixData.Data.Prefixes {
      if i>=12{info("Additional prefixes omitted");break}
      if _,_,err:=net.ParseCIDR(p.Prefix);err==nil{found("Announced prefix: %s",p.Prefix)}
    }
}
