package main

// New passive sources in v1.6. Everything is bounded (4.5 s/provider,
// 384 KB/response, 1-2 requests per entry) and source-labeled. No guessing
// personal contacts or joining accounts solely by matching display names.
import (
 "encoding/json"
 "errors"
 "fmt"
 "io"
 "net"
 "net/http"
 "net/url"
 "strconv"
 "strings"
 "time"
)

const extraTimeout=4500*time.Millisecond
var extraClient=&http.Client{
 Timeout:extraTimeout,
 CheckRedirect:func(req *http.Request,via []*http.Request)error{
  if len(via)>2{return http.ErrUseLastResponse}
  return nil
 },
}
func extraJSON(c *http.Client, raw string, dst any) error {
 req,err:=http.NewRequest(http.MethodGet,raw,nil)
 if err!=nil{return err}
 req.Header.Set("User-Agent","FlipperOne-OSINT/1.6 (+https://github.com/wasabicover258/FlipperOne-OSINT)")
 req.Header.Set("Accept","application/json")
 res,err:=c.Do(req)
 if err!=nil{return err}
 defer res.Body.Close()
 if res.StatusCode!=http.StatusOK{return fmt.Errorf("provider HTTP %d",res.StatusCode)}
 bytes,err:=io.ReadAll(io.LimitReader(res.Body,384*1024+1))
 if err!=nil{return err}
 if len(bytes)>384*1024{return errors.New("provider reply too large")}
 return json.Unmarshal(bytes,dst)
}
func extraMsg(provider string,err error){
 if err!=nil{info("%s: source unavailable (%s)",provider,shorten(err.Error(),45))}
}
func trustedSite(raw string) string {
 v:=strings.TrimSpace(raw)
 u,err:=url.Parse(v)
 if err!=nil || u.Scheme!="https" || u.User!=nil || u.Hostname()=="" {return ""}
 // A link is presented, not automatically fetched. Reject control characters.
 for _,r:=range v {if r<32 {return ""}}
 if len(v)>220{return ""}
 return v
}

// 1/16: scholarly records by NAME, always separate candidates with their own
// author IDs. Never claim an OpenAlex name candidate is the same person.
type openAlexAuthors struct{ Results []struct {
 ID string `json:"id"`
 DisplayName string `json:"display_name"`
 WorksCount int `json:"works_count"`
 ORCID string `json:"orcid"`
 Institutions []struct{
    ID string `json:"id"`
    DisplayName string `json:"display_name"`
 } `json:"last_known_institutions"`
 } `json:"results"`
}
func extraNameScholar(name string) {
 if len(strings.TrimSpace(name))<4{return}
 head("Scholarly author candidates (OpenAlex)")
 api:="https://api.openalex.org/authors?search="+url.QueryEscape(name)+"&per-page=3"
 var resp openAlexAuthors
 if err:=extraJSON(extraClient,api,&resp);err!=nil{extraMsg("OpenAlex",err);return}
 if len(resp.Results)==0 {miss("No public academic author candidates");return}
 for _,a:=range resp.Results {
  link:=trustedSite(a.ID)
  if !strings.HasPrefix(link,"https://openalex.org/") {continue}
  found("Academic author candidate: %s",a.DisplayName)
  info("Author ID / source: %s",link)
  info("Indexed publications: %d",a.WorksCount)
  for i,inst:=range a.Institutions {
   if i>=2{break}
   info("Published affiliation candidate: %s",shorten(inst.DisplayName,80))
  }
  if strings.HasPrefix(a.ORCID,"https://orcid.org/") {
   info("Public ORCID: %s",a.ORCID)
  }
  store.Add(Record{Kind:KindPerson,Value:link,Title:a.DisplayName,
      Evidence:EvUnconfirmed,Sources:sourced("openalex","Research author candidate",link),URL:link})
 }
 info("Do not equate similar names with a verified identity or email.")
}

// 2/16: exact GitHub account lookup and public repository/context metadata.
// No private emails, leaked credentials, or implicit person matching.
type githubUserProfile struct {
 Login string `json:"login"`
 Name string `json:"name"`
 Type string `json:"type"`
 Bio string `json:"bio"`
 Blog string `json:"blog"`
 Company string `json:"company"`
 PublicRepos int `json:"public_repos"`
 HTMLURL string `json:"html_url"`
}
func extraUsernameGitHub(handle string) {
 if !validUser.MatchString(handle){return}
 head("Verified platform record: GitHub")
 link:="https://api.github.com/users/"+url.PathEscape(handle)
 var g githubUserProfile
 if err:=extraJSON(extraClient,link,&g);err!=nil{extraMsg("GitHub",err);return}
 if !strings.EqualFold(g.Login,handle) || trustedSite(g.HTMLURL)=="" {return}
 found("GitHub handle exists: %s",g.Login)
 info("GitHub profile: %s",g.HTMLURL)
 info("Public repositories: %d",g.PublicRepos)
 if g.Name!="" {info("Account display name (self-declared): %s",shorten(g.Name,75))}
 if g.Bio!="" {info("Public bio: %s",shorten(g.Bio,95))}
 if g.Company!="" {info("Account affiliation (self-declared): %s",shorten(g.Company,80))}
 if safe:=trustedSite(g.Blog);safe!="" {info("Account website: %s",safe)}
 store.Add(Record{Kind:KindAccount,Value:g.HTMLURL,Title:"GitHub "+g.Login,
   Evidence:EvIndication,URL:g.HTMLURL,Sources:sourced("github-rest","GitHub public exact username record",link)})
}

// 3/16: independent mail-server transport security: DANE TLSA on MX.
// Existing SPF/DMARC/MTA-STS logic remains untouched.
func extraEmailDANE(email string){
 at:=strings.LastIndex(email,"@")
 if at<0 || !emailRe.MatchString(email){return}
 domain:=strings.ToLower(email[at+1:])
 head("Extra email-domain security: DANE")
 ctx,cancel:=dnsCtx(4)
 mxs,err:=net.DefaultResolver.LookupMX(ctx,domain)
 cancel()
 if err!=nil || len(mxs)==0 {info("DANE skipped: no MX records");return}
 sortMX:=mxs[0]
 for _,m:=range mxs {if m.Pref<sortMX.Pref {sortMX=m}}
 host:=strings.TrimSuffix(sortMX.Host,".")
 if !domainRe.MatchString(host){return}
 tlsName:="_25._tcp."+host
 records:=dohData(tlsName,"TLSA")
 if len(records)==0 {
  info("DANE TLSA: not found for primary MX (%s)",host)
  return
 }
 found("DANE TLSA: %d public record(s) on %s",len(records),host)
 info("Source: DNS-over-HTTPS query of %s",tlsName)
}

// 4/16: coarse historic German geographic landline prefixes, never owner
// identification or asserted current handset location.
var deFixedPrefixes=[]struct{code,area string}{
 {"89","Munich"},{"30","Berlin"},{"40","Hamburg"},{"69","Frankfurt am Main"},
 {"221","Cologne"},{"211","Duesseldorf"},{"711","Stuttgart"},{"341","Leipzig"},
 {"351","Dresden"},{"911","Nuremberg"},{"421","Bremen"},{"511","Hanover"},
 {"231","Dortmund"},{"201","Essen"},{"821","Augsburg"},{"241","Aachen"},
 {"6151","Darmstadt"},{"681","Saarbruecken"},{"631","Kaiserslautern"},
}
func germanDialingArea(raw string) string {
 digits:=nonDigits.ReplaceAllString(raw,"")
 if strings.HasPrefix(digits,"0049"){digits=digits[4:]}
 if strings.HasPrefix(digits,"49"){digits=digits[2:]}
 if strings.HasPrefix(digits,"0"){digits=digits[1:]}
 // Mobile numbers are not fixed line locations.
 if strings.HasPrefix(digits,"15")||strings.HasPrefix(digits,"16")||strings.HasPrefix(digits,"17"){return ""}
 best:=""
 area:=""
 for _,p:=range deFixedPrefixes {
  if strings.HasPrefix(digits,p.code) && len(p.code)>len(best){
   best=p.code;area=p.area
  }
 }
 if area==""{return ""}
 return area+" (historic geographic dialing area; NOT current location)"
}
func extraPhoneArea(raw string){
 area:=germanDialingArea(raw)
 if area==""{return}
 head("Numbering-plan context")
 found("Possible German fixed-line region: %s",area)
 info("No owner, caller location or portable carrier identity is inferred.")
}

// 5+6/16: second provider for public IP geography. An IP geolocation is
// an estimate of routing/registration context, never a device's GPS position.
type extraIPWho struct {
 Success bool `json:"success"`
 IP string `json:"ip"`
 Country string `json:"country"`
 Region string `json:"region"`
 City string `json:"city"`
 Connection struct{
  ASN int `json:"asn"`
  ISP string `json:"isp"`
  Org string `json:"org"`
 } `json:"connection"`
}
func extraIPProvider(value string){
 ip:=net.ParseIP(strings.TrimSpace(value))
 if !isPublicIP(ip){return}
 head("Independent IP provider: IPWhois")
 api:="https://ipwho.is/"+url.PathEscape(ip.String())
 var p extraIPWho
 if err:=extraJSON(extraClient,api,&p);err!=nil{extraMsg("IPWhois",err);return}
 if !p.Success || net.ParseIP(p.IP)==nil || !net.ParseIP(p.IP).Equal(ip){info("IPWhois returned no verified address match");return}
 place:=strings.TrimSpace(strings.Join(filterEmpty(p.City,p.Region,p.Country),", "))
 if place!=""{found("IP location estimate: %s",place)}
 if p.Connection.ASN>0{found("IP ASN independently reported: AS%d",p.Connection.ASN)}
 if p.Connection.ISP!=""{info("IP ISP: %s",p.Connection.ISP)}
 if p.Connection.Org!=""{info("IP organization: %s",p.Connection.Org)}
 info("Source: %s ; country/city are approximate, never a person's whereabouts.",api)
}

// 7/16: Internet Archive historical snapshot, only for the user-input
// domain. Source discovery, not a crawl of Wayback's entire archive.
type archiveAvailability struct {
 ArchivedSnapshots struct{
  Closest struct{
   Available bool `json:"available"`
   URL string `json:"url"`
   Timestamp string `json:"timestamp"`
  } `json:"closest"`
 } `json:"archived_snapshots"`
}
func extraWayback(domain string) {
 if !domainRe.MatchString(domain){return}
 head("Historic website: Internet Archive")
 endpoint:="https://archive.org/wayback/available?url="+url.QueryEscape("https://"+domain)
 var w archiveAvailability
 if err:=extraJSON(extraClient,endpoint,&w);err!=nil{extraMsg("Wayback",err);return}
 e:=w.ArchivedSnapshots.Closest
 if strings.HasPrefix(e.URL,"http://web.archive.org/") {
    e.URL="https://"+strings.TrimPrefix(e.URL,"http://")
 }
 if !e.Available || !strings.HasPrefix(e.URL,"https://web.archive.org/"){
  info("No known accessible Wayback snapshot");return
 }
 found("Archived website snapshot: %s",e.URL)
 if len(e.Timestamp)>=8{info("Archive timestamp: %s",e.Timestamp)}
 info("Source: Internet Archive Wayback availability API")
 store.Add(Record{Kind:KindDoc,Value:e.URL,Title:"Historical website of "+domain,
   Evidence:EvIndication,URL:e.URL,Sources:sourced("internet-archive","Public archived website",endpoint)})
}

// 8+9/16: Wikimedia's GeoSearch is independent of OpenStreetMap. Places
// are articles with coordinates, NOT proof of a mapped business at that point.
type geoWikiResult struct {
 Query struct{ GeoSearch []struct{
   PageID int64 `json:"pageid"`
   Title string `json:"title"`
   Dist float64 `json:"dist"`
 } `json:"geosearch"` } `json:"query"`
}
func extraWikiGeo(lat,lon float64){
 endpoint:="https://en.wikipedia.org/w/api.php?"+
  url.Values{"action":{"query"},"list":{"geosearch"},
   "gscoord":{fmt.Sprintf("%.6f|%.6f",lat,lon)},
   "gsradius":{"1000"},"gslimit":{"5"},"format":{"json"}}.Encode()
 var g geoWikiResult
 if err:=extraJSON(extraClient,endpoint,&g);err!=nil{
  extraMsg("Wikipedia nearby",err);return
 }
 head("Additional nearby Wikipedia articles")
 for _,p:=range g.Query.GeoSearch {
  if p.PageID<=0 || p.Dist>1000 {continue}
  link:="https://en.wikipedia.org/?curid="+strconv.FormatInt(p.PageID,10)
  found("Nearby Wikipedia: %s (%.0fm)",p.Title,p.Dist)
  info("Source: %s",link)
  store.Add(Record{Kind:KindDoc,Value:link,Title:p.Title,
   Evidence:EvUnconfirmed,URL:link,Sources:sourced("wikipedia-geosearch","Nearby indexed article",link)})
 }
}
