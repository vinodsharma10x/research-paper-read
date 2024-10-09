import urllib3
import warnings
import sys
import os

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Suppress NotOpenSSLWarning
warnings.filterwarnings("ignore", category=urllib3.exceptions.NotOpenSSLWarning)

from flask import Flask, request, jsonify, render_template
from Bio import Entrez, Medline
import arxiv
import requests

app = Flask(__name__)

# Replace these with your actual email and API key
PUBMED_EMAIL = "your_email@example.com"
IEEE_API_KEY = "your_ieee_api_key"

def search_pubmed(query, max_results=10, author="", journal="", year_from="", year_to="", article_type=""):
    Entrez.email = PUBMED_EMAIL  # Use the hardcoded email
    search_query = query
    if author:
        search_query += f" AND {author}[Author]"
    if journal:
        search_query += f" AND {journal}[Journal]"
    if year_from and year_to:
        search_query += f" AND {year_from}:{year_to}[Date - Publication]"
    elif year_from:
        search_query += f" AND {year_from}:3000[Date - Publication]"
    elif year_to:
        search_query += f" AND 1800:{year_to}[Date - Publication]"
    if article_type:
        search_query += f" AND {article_type}[Publication Type]"
    
    handle = Entrez.esearch(db="pubmed", term=search_query, retmax=max_results)
    record = Entrez.read(handle)
    handle.close()
    
    id_list = record["IdList"]
    handle = Entrez.efetch(db="pubmed", id=id_list, rettype="medline", retmode="text")
    records = Medline.parse(handle)
    
    articles = []
    for record in records:
        article = {
            "title": record.get("TI", "N/A"),
            "authors": record.get("AU", []),
            "journal": record.get("JT", "N/A"),
            "pubdate": record.get("DP", "N/A"),
            "pmid": record.get("PMID", "N/A"),
            "abstract": record.get("AB", "N/A"),
            "source": "PubMed"
        }
        articles.append(article)
    handle.close()
    return articles

def search_arxiv(query, max_results=10, author="", year_from="", year_to=""):
    search_query = query
    if author:
        search_query += f" AND au:{author}"
    
    client = arxiv.Client()
    search = arxiv.Search(
        query=search_query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance
    )
    
    articles = []
    for result in client.results(search):
        pub_year = result.published.year
        if (not year_from or pub_year >= int(year_from)) and (not year_to or pub_year <= int(year_to)):
            article = {
                "title": result.title,
                "authors": [author.name for author in result.authors],
                "journal": "arXiv",
                "pubdate": result.published.strftime("%Y-%m-%d"),
                "pmid": result.entry_id,
                "abstract": result.summary,
                "source": "arXiv"
            }
            articles.append(article)
    return articles

def search_ieee(query, max_results=10, author="", journal="", year_from="", year_to=""):
    base_url = "http://ieeexploreapi.ieee.org/api/v1/search/articles"
    
    params = {
        "apikey": IEEE_API_KEY,  # Use the hardcoded API key
        "format": "json",
        "max_records": max_results,
        "start_record": 1,
        "sort_order": "desc",
        "sort_field": "relevance",
        "querytext": query
    }
    
    if author:
        params["author"] = author
    if journal:
        params["publication_title"] = journal
    if year_from:
        params["start_year"] = year_from
    if year_to:
        params["end_year"] = year_to
    
    try:
        response = requests.get(base_url, params=params)
        
        if response.status_code == 403:
            if "Developer Inactive" in response.text:
                return [], "IEEE API account is not yet active. Please check your account status."
            else:
                return [], f"IEEE API access forbidden. Response content: {response.text}"
        
        response.raise_for_status()
        data = response.json()
        
        articles = []
        for article in data.get("articles", []):
            articles.append({
                "title": article.get("title", "N/A"),
                "authors": [author.get("full_name", "N/A") for author in article.get("authors", {}).get("authors", [])],
                "journal": article.get("publication_title", "N/A"),
                "pubdate": article.get("publication_year", "N/A"),
                "pmid": article.get("article_number", "N/A"),
                "abstract": article.get("abstract", "N/A"),
                "source": "IEEE Xplore"
            })
        
        return articles, None
    except requests.exceptions.RequestException as e:
        error_message = f"Error making request to IEEE API: {e}"
        if hasattr(e, 'response') and e.response is not None:
            error_message += f"\nResponse content: {e.response.text}"
        return [], error_message

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    data = request.json
    query = data.get('query', '')
    max_results = int(data.get('max_results', 10))
    sources = data.get('sources', ['pubmed', 'arxiv', 'ieee'])
    author = data.get('author', '')
    journal = data.get('journal', '')
    year_from = data.get('year_from', '')
    year_to = data.get('year_to', '')
    article_type = data.get('article_type', '')
    
    all_articles = []
    errors = []
    
    if 'pubmed' in sources:
        try:
            pubmed_articles = search_pubmed(query, max_results // len(sources), author, journal, year_from, year_to, article_type)
            all_articles.extend(pubmed_articles)
        except Exception as e:
            errors.append(f"PubMed search error: {str(e)}")
    
    if 'arxiv' in sources:
        try:
            arxiv_articles = search_arxiv(query, max_results // len(sources), author, year_from, year_to)
            all_articles.extend(arxiv_articles)
        except Exception as e:
            errors.append(f"arXiv search error: {str(e)}")
    
    if 'ieee' in sources:
        try:
            ieee_articles, ieee_error = search_ieee(query, max_results // len(sources), author=author, journal=journal, year_from=year_from, year_to=year_to)
            all_articles.extend(ieee_articles)
            if ieee_error:
                errors.append(f"IEEE Xplore search error: {ieee_error}")
        except Exception as e:
            errors.append(f"IEEE Xplore search error: {str(e)}")
    
    return jsonify({"articles": all_articles, "errors": errors})

if __name__ == '__main__':
    app.run(debug=True)