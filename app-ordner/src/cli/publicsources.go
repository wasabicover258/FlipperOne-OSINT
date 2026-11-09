package main

// publicsources.go: independent public-source discovery for names.
// Search results are *candidates*, never automated identity linkages.

import (
    "encoding/json"
    "fmt"
    "net/http"
    "net/url"
)

func runPublicNameExtras(name string) {
    head("Wikipedia article candidates")
    wikiURL:="https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=3&srsearch="+url.QueryEscape(name)
    var w struct {
        Query struct {
            Search []struct{
                Title string `json:"title"`
                PageID int `json:"pageid"`
            } `json:"search"`
        } `json:"query"`
    }
    if resp,raw,err:=get(client,wikiURL);err==nil&&resp.StatusCode==http.StatusOK&&json.Unmarshal(raw,&w)==nil{
        if len(w.Query.Search)==0{miss("No matching English Wikipedia article")}
        for _,a:=range w.Query.Search{
            if a.Title==""||a.PageID<=0{continue}
            link:="https://en.wikipedia.org/?curid="+fmt.Sprint(a.PageID)
            found("%s",a.Title)
            info("Source: %s",link)
            store.Add(Record{Kind:KindDoc,Value:link,Title:a.Title,
                Evidence:EvUnconfirmed,URL:link,Sources:sourced("wikipedia","Wikipedia search",link)})
        }
    }else{
        info("Wikipedia unavailable (network or rate limit).")
    }
    head("GitHub account candidates")
    // q=<name> is a candidate search and may match multiple unrelated users.
    // Never assume that an account is owned by the searched person.
    githubURL:="https://api.github.com/search/users?per_page=3&q="+url.QueryEscape(name+" in:fullname")
    var gh struct {
        Items []struct{
            Login string `json:"login"`
            HTMLURL string `json:"html_url"`
        } `json:"items"`
    }
    if resp,raw,err:=get(client,githubURL);err==nil&&resp.StatusCode==http.StatusOK&&json.Unmarshal(raw,&gh)==nil{
        for _,a:=range gh.Items{
            u,err:=url.Parse(a.HTMLURL)
            if err!=nil||u.Scheme!="https"||u.Host!="github.com"{continue}
            emit("?",fmt.Sprintf("Possible public GitHub profile: %s",a.Login))
            info("Source: %s",a.HTMLURL)
            store.Add(Record{Kind:KindAccount,Value:a.HTMLURL,Title:a.Login,
                Evidence:EvUnconfirmed,URL:a.HTMLURL,Sources:sourced("github","GitHub public user search",githubURL)})
        }
    }else{
        info("GitHub candidate search unavailable (network or API limit).")
    }
    info("Names and usernames alone do not prove a common identity.")
}
