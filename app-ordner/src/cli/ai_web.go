package main

// ai_web.go: grounded public web/document discovery for OSINT 2.0.
// Brave API is optional, configured only via an environment variable.
// Wikipedia + OpenAlex remain available without paid search credentials.
// Search summaries never claim two namesakes to be the same person.

import (
  "encoding/json"
  "fmt"
  "html"
  "io"
  "net"
  "os"
  "net/http"
  "net/url"
  "regexp"
  "sort"
  "strings"
  "time"
)

type researchHit struct {
  Title string
  URL string
  Excerpt string
  Provider string
  Published string
  PDF bool
  PDFPage int
  Quality int
}
type braveWebResponse struct {
  Web struct {
    Results []struct {
      Title string `json:"title"`
      URL string `json:"url"`
      Description string `json:"description"`
      PageAge string `json:"page_age"`
      ContentType string `json:"content_type"`
      ExtraSnippets []string `json:"extra_snippets"`
    } `json:"results"`
  } `json:"web"`
}
type wikiPublicSearch struct {
  Query struct {
    Search []struct {
      PageID int64 `json:"pageid"`
      Title string `json:"title"`
      Snippet string `json:"snippet"`
      Timestamp string `json:"timestamp"`
    } `json:"search"`
  } `json:"query"`
}
type openAlexPapers struct {
  Results []struct {
    ID string `json:"id"`
    Title string `json:"title"`
    PublicationYear int `json:"publication_year"`
    PrimaryLocation struct {
      LandingPageURL string `json:"landing_page_url"`
      PDFURL string `json:"pdf_url"`
    } `json:"primary_location"`
  } `json:"results"`
}

var tagRE=regexp.MustCompile("<[^>]*>")
var headingWhitespace=regexp.MustCompile(`\s+`)

func plainSnippet(s string) string {
  s=html.UnescapeString(tagRE.ReplaceAllString(s," "))
  s=headingWhitespace.ReplaceAllString(s," ")
  return shorten(strings.TrimSpace(s),440)
}

// Only show ordinary HTTPS public source links. Never use query results as
// instructions or send secrets to arbitrary third-party URLs.
func publicSourceURL(raw string) string {
  u,err:=url.Parse(strings.TrimSpace(raw))
  if err!=nil||u.Scheme!="https"||u.User!=nil||u.Hostname()==""||u.Port()!="" {return ""}
  if len(raw)>500 || strings.ContainsAny(raw,string([]byte{13,10,9})) {return ""}
  host:=strings.ToLower(u.Hostname())
  if host=="localhost"||strings.HasSuffix(host,".local")||strings.HasSuffix(host,".internal"){return ""}
  if ip:=netParseIP(host);ip!=nil && !isPublicIP(ip) {return ""}
  u.Fragment=""
  q:=u.Query()
  for name:=range q {
    low:=strings.ToLower(name)
    if strings.HasPrefix(low,"utm_")||low=="fbclid"||low=="gclid" {
      q.Del(name)
    }
  }
  u.RawQuery=q.Encode()
  return u.String()
}

// Defined in ai_web.go to keep the API boundary local and easy to mock.
func netParseIP(s string) net.IP { return net.ParseIP(s) }

func hitKey(h researchHit) string {
  if u:=publicSourceURL(h.URL);u!="" {
    return strings.TrimSuffix(strings.ToLower(u),"/")
  }
  return strings.ToLower(strings.TrimSpace(h.Title))
}
func uniqueWebHits(in []researchHit,limit int) []researchHit {
  var out []researchHit
  seen:=map[string]int{}
  for _,h:=range in {
    h.URL=publicSourceURL(h.URL)
    if h.URL=="" || h.Title=="" {continue}
    k:=hitKey(h)
    if i,ok:=seen[k];ok {
      // Preserve a substantive excerpt from the better of the two sources.
      if len(h.Excerpt)>len(out[i].Excerpt){out[i].Excerpt=h.Excerpt}
      if h.Quality>out[i].Quality{out[i].Quality=h.Quality}
      continue
    }
    seen[k]=len(out)
    out=append(out,h)
  }
  sort.SliceStable(out,func(i,j int)bool{
    if out[i].Quality!=out[j].Quality{return out[i].Quality>out[j].Quality}
    return i<j
  })
  if limit>0 && len(out)>limit {out=out[:limit]}
  return out
}

func braveWebSearch(query,key string,fetch *http.Client)([]researchHit,error) {
  if len(query)<2||len(query)>220 {return nil,fmt.Errorf("invalid search phrase length")}
  v:=url.Values{"q":{query},"count":{"8"},"search_lang":{"en"},"extra_snippets":{"true"}}
  req,err:=http.NewRequest(http.MethodGet,"https://api.search.brave.com/res/v1/web/search?"+v.Encode(),nil)
  if err!=nil{return nil,err}
  req.Header.Set("X-Subscription-Token",key)
  req.Header.Set("Accept","application/json")
  req.Header.Set("User-Agent","FlipperOne-OSINT/2.0 (https://github.com/wasabicover258/FlipperOne-OSINT)")
  resp,err:=fetch.Do(req)
  if err!=nil{return nil,err}
  defer resp.Body.Close()
  if resp.StatusCode!=http.StatusOK{return nil,fmt.Errorf("Brave HTTP %d",resp.StatusCode)}
  bytes,err:=io.ReadAll(io.LimitReader(resp.Body,1024*1024+1))
  if err!=nil{return nil,err}
  if len(bytes)>1024*1024{return nil,fmt.Errorf("Brave response too large")}
  var payload braveWebResponse
  if err:=json.Unmarshal(bytes,&payload);err!=nil{return nil,err}
  hits:=make([]researchHit,0,len(payload.Web.Results))
  for _,r:=range payload.Web.Results {
    link:=publicSourceURL(r.URL)
    if link==""{continue}
    desc:=plainSnippet(r.Description)
    if desc=="" && len(r.ExtraSnippets)>0 {desc=plainSnippet(r.ExtraSnippets[0])}
    isPDF:=strings.HasSuffix(strings.ToLower(strings.Split(link,"?")[0]),".pdf")||
        strings.Contains(strings.ToLower(r.ContentType),"pdf")
    quality:=2
    if isPDF{quality++}
    hits=append(hits,researchHit{
      Title:plainSnippet(r.Title),URL:link,Excerpt:desc,Provider:"Brave Search",
      Published:plainSnippet(r.PageAge),PDF:isPDF,Quality:quality,
    })
  }
  return hits,nil
}

func wikipediaWebSearch(query string,fetch *http.Client)([]researchHit,error) {
  v:=url.Values{"action":{"query"},"list":{"search"},"srsearch":{query},
    "srnamespace":{"0"},"srlimit":{"5"},"format":{"json"}}
  req,err:=http.NewRequest(http.MethodGet,
    "https://en.wikipedia.org/w/api.php?"+v.Encode(),nil)
  if err!=nil{return nil,err}
  req.Header.Set("User-Agent","FlipperOne-OSINT/2.0 (https://github.com/wasabicover258/FlipperOne-OSINT)")
  resp,err:=fetch.Do(req)
  if err!=nil{return nil,err}
  defer resp.Body.Close()
  if resp.StatusCode!=200{return nil,fmt.Errorf("Wikipedia HTTP %d",resp.StatusCode)}
  bytes,err:=io.ReadAll(io.LimitReader(resp.Body,512*1024+1))
  if err!=nil{return nil,err}
  if len(bytes)>512*1024{return nil,fmt.Errorf("Wikipedia response too large")}
  var result wikiPublicSearch
  if err:=json.Unmarshal(bytes,&result);err!=nil{return nil,err}
  var out []researchHit
  for _,p:=range result.Query.Search {
    if p.PageID<=0 {continue}
    out=append(out,researchHit{
      Title:plainSnippet(p.Title),URL:fmt.Sprintf("https://en.wikipedia.org/?curid=%d",p.PageID),
      Excerpt:plainSnippet(p.Snippet),Provider:"Wikipedia Search",
      Published:p.Timestamp,Quality:1,
    })
  }
  return out,nil
}

func openAlexWorksSearch(query string,fetch *http.Client)([]researchHit,error) {
  v:=url.Values{"search":{query},"per-page":{"5"}}
  req,err:=http.NewRequest(http.MethodGet,"https://api.openalex.org/works?"+v.Encode(),nil)
  if err!=nil{return nil,err}
  req.Header.Set("User-Agent","FlipperOne-OSINT/2.0 (https://github.com/wasabicover258/FlipperOne-OSINT)")
  resp,err:=fetch.Do(req)
  if err!=nil{return nil,err}
  defer resp.Body.Close()
  if resp.StatusCode!=200{return nil,fmt.Errorf("OpenAlex HTTP %d",resp.StatusCode)}
  bytes,err:=io.ReadAll(io.LimitReader(resp.Body,1024*1024+1))
  if err!=nil{return nil,err}
  if len(bytes)>1024*1024{return nil,fmt.Errorf("OpenAlex response too large")}
  var result openAlexPapers
  if err:=json.Unmarshal(bytes,&result);err!=nil{return nil,err}
  var out []researchHit
  for _,p:=range result.Results {
    link:=publicSourceURL(p.PrimaryLocation.LandingPageURL)
    if link=="" {link=publicSourceURL(p.ID)}
    if link==""||p.Title==""{continue}
    pdfURL:=publicSourceURL(p.PrimaryLocation.PDFURL)
    isPDF:=pdfURL!=""
    // Prefer the published open document, not an inferred private profile.
    if isPDF {link=pdfURL}
    out=append(out,researchHit{
      Title:plainSnippet(p.Title),URL:link,
      Excerpt:fmt.Sprintf("Public academic work from %d. Source: OpenAlex.",p.PublicationYear),
      Provider:"OpenAlex",Published:fmt.Sprint(p.PublicationYear),PDF:isPDF,Quality:1,
    })
  }
  return out,nil
}

func runAIWebResearch(query string) {
  head("Smart web & document research")
  info("Searching public documents and pages; matching names alone is not identity proof.")
  // Always useful without credentials; no account registration checks.
  c:=&http.Client{Timeout:8500*time.Millisecond}
  var all []researchHit
  if key:=strings.TrimSpace(os.Getenv("BRAVE_SEARCH_API_KEY"));key!="" {
    queries:=[]string{`"`+query+`"`,`"`+query+`" filetype:pdf`}
    // Only two bounded searches, rather than unlimited OSINT pivots.
    for _,q:=range queries{
      foundHits,err:=braveWebSearch(q,key,c)
      if err!=nil{info("Brave search: %s",shorten(err.Error(),70));continue}
      all=append(all,foundHits...)
    }
  } else {
    info("Broad web/PDF discovery needs BRAVE_SEARCH_API_KEY; public fallback active.")
  }
  if hits,err:=wikipediaWebSearch(query,c);err==nil {
    all=append(all,hits...)
  } else {info("Wikipedia temporarily unavailable: %s",shorten(err.Error(),55))}
  if hits,err:=openAlexWorksSearch(query,c);err==nil {
    all=append(all,hits...)
  } else {info("OpenAlex works temporarily unavailable: %s",shorten(err.Error(),55))}
  hits:=uniqueWebHits(all,22)
  // PDF text analysis is bounded and never required for a basic search.
  pdfChecked:=0
  for i:=range hits {
    if !hits[i].PDF || pdfChecked>=2 {continue}
    pdfChecked++
    if excerpt,page,err:=readPublicPDFExcerpt(hits[i].URL,query);err==nil&&excerpt!="" {
      hits[i].Excerpt=excerpt
      hits[i].PDFPage=page
      hits[i].Quality+=2
    }
  }
  if len(hits)==0{miss("No usable public web results from configured providers");return}
  for i,h:=range hits {
    typeName:="Web page"
    if h.PDF{typeName="PDF document"}
    found("%s: %s",typeName,shorten(h.Title,130))
    if h.PDFPage>0{info("PDF text match: page %d",h.PDFPage)}
    if h.Published!=""{info("Date (provider): %s",shorten(h.Published,32))}
    if h.Excerpt!=""{info("Excerpt: %s",shorten(h.Excerpt,260))}
    info("Source: %s",h.URL)
    store.Add(Record{Kind:KindDoc,Value:h.URL,Title:h.Title,URL:h.URL,
      Evidence:EvUnconfirmed,Sources:sourced("ai-web",h.Provider,h.URL),
      Note:shorten(h.Excerpt,210)})
    if i>=20 {break}
  }
  info("Sources contain search candidates. Verify text and context before attributing them to a person.")
}
