import os
import json
import requests
import base64
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from database import SessionLocal, ScrapedKnowledge

TEXT_MODEL = "models/gemini-flash-latest"
IMAGE_MODEL = "models/gemini-flash-latest"

ORG_CONTEXT = """
Empresa: VisionAI — Enxergando o Futuro com Inteligência
LinkedIn: linkedin.com/company/visionaicombr
Slogan: "Enxergando o Futuro com Inteligência"
Website: https://visionai.com.br

Linhas de Serviço (extraídas do site real):
1. IA Multimodal & Atendimento — Atendimento automático que analisa áudio, vídeo e imagem juntos em segundos. Assistente de voz com memória de contexto. URA com compreensão contextual.
2. Visão Computacional & Edge — Análise automática de câmeras existentes processando localmente sem nuvem. Fiscalização automática de EPIs. Rastreamento de ativos e logística. Mapas de calor de ocupação.
3. Realidade Mista & EdTech — Treinamentos em Realidade Mista (Meta Quest 3). Simulação de cenários perigosos. Treinamento de empatia para neurodiversidade. Acessibilidade visual e sonora.
4. Visão Agro-Industrial — Monitoramento de lavouras com câmeras e drones. Detecção de pragas antes da perda da safra. Manutenção preditiva industrial. Processamento local sem internet.
5. Geração de Conteúdo & Analytics — Produção automatizada de vídeos e apresentações (3 semanas → 2 dias). Análise de engajamento. Apresentações comerciais personalizadas por segmento.
6. Governança Corporativa & Intelligence — Sites corporativos, painéis de inteligência de mercado, rastreamento automático de concorrência.

Diferenciais técnicos:
- Processamento na borda (Edge AI) sem dependência de nuvem
- Integração com câmeras já instaladas pelo cliente
- IA que processa áudio, vídeo e documentos simultaneamente
- Resultados: +15% produtividade agro, 95% precisão em atendimento, ciclo de conteúdo de 3 semanas para 2 dias
- Ambiente VR multi-usuário com física realista

Tom de voz: Técnico, orientado a resultado real, sem hype, direto ao ponto
Idioma: Português do Brasil (profissional mas acessível)
Público-alvo: C-Levels, Heads de Operação, Diretores de TI, Gestores Industriais e do Agronegócio
"""

class GeminiStudio:
    def __init__(self):
        raw_key = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_KEY") or ""
        if "GEMINI_API_KEY=" in raw_key:
            raw_key = raw_key.split("GEMINI_API_KEY=")[-1]
        api_key = raw_key.strip().strip("'").strip('"')
        try:
            self.client = genai.Client(api_key=api_key, http_options={'api_version': 'v1alpha'})
        except Exception:
            self.client = genai.Client(api_key=api_key)
        self.model = TEXT_MODEL
        self.fallback_models = ["gemini-3.5-flash", "gemini-3-pro-preview", "gemini-2.5-flash", "gemini-3.1-flash-lite"]
        self.scraped_context = self._scrape_visionai_website()

    def _get_dynamic_brand_dna(self) -> dict:
        """Carrega os dados do Brand DNA salvos no banco SQLite de forma 100% dinâmica."""
        db = SessionLocal()
        try:
            from database import BrandDNA
            dna = db.query(BrandDNA).first()
            if dna:
                return {
                    "company_name": dna.company_name or "VisionAI",
                    "website_url": dna.website_url or "https://visionai.com.br",
                    "industry": dna.industry or "Inteligência Artificial & Computação de Borda",
                    "target_audience": dna.target_audience or "C-Levels, Diretores de TI, Heads de Operações",
                    "tone_of_voice": dna.tone_of_voice or "Visionário, Técnico, Pragmático e Orientado a ROI",
                    "core_services": dna.core_services or "IA Multimodal, Visão Computacional, Realidade Mista",
                    "differentials": dna.differentials or "Processamento Edge, IA Multimodal",
                    "content_pillars": dna.content_pillars or "Conceitos & Ciência, Inovação"
                }
        except Exception as e:
            print(f"Erro ao carregar BrandDNA do DB: {e}")
        finally:
            db.close()
            
        return {
            "company_name": "VisionAI",
            "website_url": "https://visionai.com.br",
            "industry": "Inteligência Artificial & Computação de Borda",
            "target_audience": "C-Levels, Diretores de TI, Heads de Operações",
            "tone_of_voice": "Visionário, Técnico, Pragmático",
            "core_services": "IA Multimodal, Visão Computacional, Realidade Mista",
            "differentials": "Processamento Edge, IA Multimodal",
            "content_pillars": "Conceitos & Ciência, Inovação"
        }

    def _get_brand_dna_context(self) -> str:
        """Gera o contexto da empresa para os prompts de IA de forma 100% dinâmica a partir do DB."""
        dna = self._get_dynamic_brand_dna()
        return f"""
EMPRESA: {dna['company_name']}
WEBSITE: {dna['website_url']}
SETOR/INDÚSTRIA: {dna['industry']}
PÚBLICO-ALVO: {dna['target_audience']}
TOM DE VOZ INSTITUCIONAL: {dna['tone_of_voice']}
SERVIÇOS / SOLUÇÕES: {dna['core_services']}
DIFERENCIAIS COMPETITIVOS: {dna['differentials']}
PILARES DE CONTEÚDO: {dna['content_pillars']}
"""

    def _fetch_full_paper_or_url_content(self, url: str) -> str:
        """
        Faz a leitura AO VIVO E EM TEMPO REAL (no momento exato da geração) do PDF ou artigo da web a partir da URL.
        Não utiliza nenhum cache estático, garantindo a leitura atualizada do paper completo.
        """
        import requests, re, io
        from pypdf import PdfReader

        if not url or not url.startswith("http"):
            return ""

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VisionAI Live Scraper"}

        # 1. Identificação de ID do ArXiv / HuggingFace na URL (ex: 2401.12345 ou 2607.27372)
        arxiv_match = re.search(r'(\d{4}\.\d{4,5})', url)
        if arxiv_match:
            paper_id = arxiv_match.group(1)
            pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"
            print(f"🔥 Baixando e lendo PDF do paper AO VIVO no momento da geração: {pdf_url}...")
            try:
                r = requests.get(pdf_url, headers=headers, timeout=25)
                if r.status_code == 200 and len(r.content) > 1000:
                    reader = PdfReader(io.BytesIO(r.content))
                    extracted_text = ""
                    for page in reader.pages[:5]: # Lê até 5 páginas do paper (suficiente para abstract e introdução)
                        txt = page.extract_text()
                        if txt:
                            extracted_text += txt + "\n"
                    if len(extracted_text) > 300:
                        print(f"✅ PDF do paper lido na íntegra ao vivo ({len(extracted_text)} caracteres).")
                        return extracted_text[:20000]
            except Exception as e:
                print(f"Falha no download ao vivo do PDF ArXiv {pdf_url}: {e}")

        # 2. Se for uma página do HuggingFace Papers sem ID direto na URL, busca a URL do PDF no HTML
        if "huggingface.co/papers" in url or "arxiv.org" in url:
            try:
                r_page = requests.get(url, headers=headers, timeout=15)
                if r_page.status_code == 200:
                    page_html = r_page.text
                    pdf_link_match = re.search(r'https?://arxiv\.org/pdf/\d{4}\.\d{4,5}(?:\.pdf)?', page_html)
                    if pdf_link_match:
                        target_pdf = pdf_link_match.group(0)
                        if not target_pdf.endswith('.pdf'): target_pdf += '.pdf'
                        r_pdf = requests.get(target_pdf, headers=headers, timeout=25)
                        if r_pdf.status_code == 200:
                            reader = PdfReader(io.BytesIO(r_pdf.content))
                            extracted_text = ""
                            for page in reader.pages[:5]:
                                txt = page.extract_text()
                                if txt: extracted_text += txt + "\n"
                            if len(extracted_text) > 300:
                                print(f"✅ PDF extraído do HTML do HuggingFace e lido ao vivo ({len(extracted_text)} caracteres).")
                                return extracted_text[:10000]
            except Exception as e:
                print(f"Falha ao raspar página HTML de paper: {e}")

        # 3. Leitura ao vivo de PDF direto
        if url.lower().endswith(".pdf"):
            try:
                r = requests.get(url, headers=headers, timeout=25)
                if r.status_code == 200:
                    reader = PdfReader(io.BytesIO(r.content))
                    extracted_text = ""
                    for page in reader.pages[:5]:
                        txt = page.extract_text()
                        if txt: extracted_text += txt + "\n"
                    if len(extracted_text) > 300:
                        return extracted_text[:20000]
            except Exception as e:
                print(f"Erro ao extrair PDF direto ao vivo {url}: {e}")

        # 4. Leitura ao vivo de página web genérica (Artigos / notícias)
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                html_text = r.text
                clean_text = re.sub(r'<script[^>]*>.*?</script>', '', html_text, flags=re.DOTALL)
                clean_text = re.sub(r'<style[^>]*>.*?</style>', '', clean_text, flags=re.DOTALL)
                clean_text = re.sub(r'<[^>]+>', ' ', clean_text)
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                if len(clean_text) > 200:
                    return clean_text[:15000]
        except Exception as e:
            print(f"Erro no web scraping ao vivo da URL {url}: {e}")

    def _safe_json_loads(self, text: str):
        """Sanitização avançada e parsing seguro de JSON gerado por LLMs com auto-reparo de truncamento."""
        import json, re
        if not text or not isinstance(text, str):
            return None
        clean = text.replace("```json", "").replace("```", "").strip()
        clean = re.sub(r'\[\d+\]', '', clean)
        clean = re.sub(r',(?=\s*[\}\]])', '', clean)
        
        start = clean.find("[")
        if start != -1:
            json_str = clean[start:]
            end = json_str.rfind("]")
            if end != -1:
                json_str = json_str[:end+1]
            else:
                last_obj_end = json_str.rfind("}")
                if last_obj_end != -1:
                    json_str = json_str[:last_obj_end+1] + "\n]"
            
            try:
                return json.loads(json_str, strict=False)
            except Exception:
                sanitized = re.sub(r'[\r\n]+', ' ', json_str)
                sanitized = re.sub(r',(?=\s*\])', '', sanitized)
                if sanitized.count('"') % 2 != 0:
                    sanitized += '"}'
                    if not sanitized.endswith("]"):
                        sanitized += "\n]"
                try:
                    return json.loads(sanitized, strict=False)
                except Exception as e:
                    print(f"Erro no safe_json_loads: {e}")
        return None

    def _translate_papers_to_ptbr(self, raw_papers: list) -> list:
        """Tradução e enriquecimento executivo B2B de papers acadêmicos em inglês para Português do Brasil (PT-BR) baseados na leitura real do PDF."""
        import re, json
        if not raw_papers:
            return []

        all_translated = []
        chunk_size = 2

        for i in range(0, len(raw_papers), chunk_size):
            chunk = raw_papers[i:i+chunk_size]
            prompt_papers = []
            for idx, p in enumerate(chunk):
                paper_url = p.get("paper_url") or p.get("paper_id") or ""
                real_pdf_text = ""
                if paper_url:
                    real_pdf_text = self._fetch_full_paper_or_url_content(paper_url)
                
                prompt_papers.append({
                    "index": idx,
                    "paper_id": p.get("paper_id", f"paper_{idx}"),
                    "original_title": p.get("title", ""),
                    "original_summary": p.get("summary", ""),
                    "real_pdf_text": real_pdf_text[:2000] if real_pdf_text else ""
                })
            
            prompt = f"""
Você é um Tradutor Técnico e Especialista em Inteligência Artificial da VizionAI (https://visionai.com.br).
SUA MISSÃO: Analise a leitura dos artigos e crie uma síntese técnica didática em PORTUGUÊS DO BRASIL (PT-BR) para a lista de {len(chunk)} papers acadêmicos abaixo.

REGRAS RÍGIDAS DE TRADUÇÃO & CONTEÚDO:
1. **title**: Crie um título magnético, claro, didático e de alta autoridade técnico-executiva em PORTUGUÊS DO BRASIL.
2. **summary**: Crie uma explicação didática de 2 a 3 frases em PORTUGUÊS DO BRASIL sobre o conteúdo do artigo e a relevância prática.
3. **pdf_preview_ptbr**: Crie uma PRÉVIA COMPLETA DO PDF EM PORTUGUÊS DO BRASIL (3 a 4 parágrafos ricos baseados na leitura do PDF real) detalhando:
   - O problema científico/técnico resolvido pelo estudo.
   - A inovação de arquitetura/algoritmo proposta pelos autores.
   - Resultados empíricos, métricas e benchmarks medidos.
   - A aplicação prática e ROI para empresas B2B e tecnologia.
4. **Mantenha o campo `index` exato (0, 1, 2, ...)** de cada item.

PAPERS PARA TRADUZIR:
{json.dumps(prompt_papers, ensure_ascii=False, indent=2)}

Responda APENAS com um array JSON válido sem qualquer bloco de código markdown ```json:
[
  {{
    "index": 0,
    "title": "Título explicativo em Português do Brasil",
    "summary": "Explicação didática do conteúdo em Português do Brasil",
    "pdf_preview_ptbr": "Prévia estruturada completa do PDF em Português do Brasil (parágrafos ricos com conceitos, métricas e aplicação B2B)"
  }}
]
"""
            try:
                raw = self._generate(prompt, temperature=0.2)
                translated_chunk = self._safe_json_loads(raw)
                if isinstance(translated_chunk, list) and len(translated_chunk) > 0:
                    for idx, orig in enumerate(chunk):
                        item_t = None
                        for t in translated_chunk:
                            if str(t.get("index")) == str(idx):
                                item_t = t
                                break
                        if not item_t and idx < len(translated_chunk):
                            item_t = translated_chunk[idx]

                        if item_t and item_t.get("title"):
                            merged = dict(orig)
                            merged["title"] = item_t.get("title", orig.get("title"))
                            merged["summary"] = item_t.get("summary", orig.get("summary"))
                            merged["pdf_preview_ptbr"] = item_t.get("pdf_preview_ptbr", item_t.get("summary", ""))
                            all_translated.append(merged)
                        else:
                            all_translated.append(orig)
                else:
                    all_translated.extend(chunk)
            except Exception as e:
                print(f"Tradução do lote de papers para PT-BR falhou: {e}")
                all_translated.extend(chunk)

        print(f"✅ Total de {len(all_translated)} papers traduzidos e mapeados para PT-BR com leitura real de PDF.")
        return all_translated

    def fetch_huggingface_trending_papers(self, query: str = None) -> dict:
        """
        Busca os papéis de pesquisa acadêmica em alta no HuggingFace / ArXiv ou por tema específico.
        Garante que todo o conteúdo seja retornado em PORTUGUÊS DO BRASIL (PT-BR) com títulos didáticos, explicação do match e prévia completa do PDF.
        """
        import requests, json, re
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VisionAI Corporate Bot"}
        papers = []
        
        # 1. Se for uma busca por tema específico do usuário, utiliza busca ao vivo com Google Search Grounding para achar os papers exatos que dão match
        if query and query.strip():
            try:
                grounding_prompt = f"""
Pesquise na internet papers acadêmicos, artigos científicos e pesquisas RECENTES (2024 a 2026) no ArXiv ou HuggingFace sobre o tema específico: '{query}'.

SUA MISSÃO: Retorne de 4 a 5 papers acadêmicos reais que deem MATCH PERFEITO com o tema '{query}'.

Responda APENAS com um array JSON no formato (sem qualquer bloco de código markdown ```json):
[
  {{
    "paper_id": "ID do ArXiv (ex: 2502.16950)",
    "title": "Original Title of the paper",
    "summary": "Original abstract overview",
    "authors": "Main authors",
    "paper_url": "https://arxiv.org/abs/XXXX.XXXXX ou https://huggingface.co/papers/XXXX.XXXXX",
    "published_at": "2025",
    "source": "ArXiv / HuggingFace Papers"
  }}
]
"""
                raw = self._generate_with_search(grounding_prompt, temperature=0.2)
                grounded_papers = self._safe_json_loads(raw)
                if isinstance(grounded_papers, list):
                    for p in grounded_papers:
                        if isinstance(p, dict) and p.get("title"):
                            if isinstance(p.get("authors"), list):
                                p["authors"] = ", ".join(p["authors"])
                            papers.append(p)
            except Exception as e:
                print(f"Grounding Papers por tema '{query}' falhou: {e}")

            if papers:
                papers = self._translate_papers_to_ptbr(papers)

            return {"ok": True, "count": len(papers), "papers": papers}

        # 2. Caso contrário (sem busca específica), traz os daily papers do HuggingFace (limitado aos 5 principais)
        try:
            hf_url = "https://huggingface.co/api/daily_papers"
            resp = requests.get(hf_url, headers=headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                for item in data[:5]:
                    paper_data = item.get("paper", {})
                    paper_id = paper_data.get("id", "")
                    title = paper_data.get("title", "")
                    summary = paper_data.get("summary", "") or paper_data.get("abstract", "")
                    authors_list = [a.get("name", "") for a in paper_data.get("authors", []) if isinstance(a, dict)]
                    authors_str = ", ".join(authors_list[:3]) if authors_list else "Pesquisadores IA"
                    paper_url = f"https://huggingface.co/papers/{paper_id}" if paper_id else "https://huggingface.co/papers"
                    
                    papers.append({
                        "paper_id": paper_id,
                        "title": title,
                        "summary": summary[:300] + ("..." if len(summary) > 300 else ""),
                        "authors": authors_str,
                        "paper_url": paper_url,
                        "published_at": paper_data.get("publishedAt", "")[:10],
                        "source": "HuggingFace Papers"
                    })
        except Exception as e:
            print(f"Erro na API HuggingFace Papers: {e}")

        # Se houver papers capturados da API, realiza a tradução e enriquecimento executivo para PT-BR
        if papers:
            papers = self._translate_papers_to_ptbr(papers)

        return {"ok": True, "count": len(papers), "papers": papers}

    def _scrape_visionai_website(self) -> str:
        """Scrape limpo do site e bundles da SPA visionai.com.br para extrair conteúdo das 6 linhas de serviço."""
        import re
        from database import init_db
        init_db()
        db = SessionLocal()
        try:
            # Cache: se já foi feito scraping recente (< 24h), usa do banco
            knowledge = db.query(ScrapedKnowledge).filter_by(category="institucional_v2").first()
            if knowledge and knowledge.content and len(knowledge.content) > 100:
                return f"\n\nCONTEÚDO DO SITE VISIONAI.COM.BR:\n{knowledge.content}"
            
            home_resp = requests.get("https://visionai.com.br", timeout=4)
            js_urls = re.findall(r'/assets/[^"]+\.js', home_resp.text)
            
            extracted = []
            js_code_words = {'function', 'document', 'var ', 'const ', 'return', 'element', 'import',
                             'catch', 'math', 'void ', '==', '=>', 'childlist', 'undefined', 'props',
                             'classname', 'queryselectorall', 'addeventlistener', 'dataset', 'innerhtml'}
            
            for js_path in js_urls[:2]:
                try:
                    js_resp = requests.get(f"https://visionai.com.br{js_path}", timeout=4)
                    content = js_resp.text
                    strings = re.findall(r'"([^"\\]{25,300})"', content)
                    seen = set()
                    for t in strings:
                        t = t.strip()
                        t_lower = t.lower()
                        if t in seen or t.startswith('http') or len(t.split()) < 3:
                            continue
                        if any(w in t_lower for w in js_code_words):
                            continue
                        seen.add(t)
                        extracted.append(t)
                except Exception:
                    continue
            
            if extracted:
                text = "\n".join(extracted[:50])
                if knowledge:
                    knowledge.content = text
                else:
                    db.add(ScrapedKnowledge(category="institucional_v2", url="https://visionai.com.br", content=text))
                db.commit()
                return f"\n\nCONTEÚDO DO SITE VISIONAI.COM.BR:\n{text}"
        except Exception as e:
            print(f"Aviso no scraping do site visionai.com.br: {e}")
        finally:
            db.close()
        return ""

    def _generate(self, prompt: str, temperature: float = 0.8) -> str:
        for m in self.fallback_models:
            try:
                response = self.client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=2048,
                    ),
                )
                self.model = m
                return response.text or ""
            except Exception as e:
                print(f"Modelo {m} falhou em _generate: {e}")
                continue
        return f"[Erro Gemini: Nenhum modelo disponível para a chave configurada]"

    def _safe_parse_json(self, raw_text: str):
        """Parse de JSON extremamente resiliente para saídas de modelos LLM."""
        if not raw_text:
            return None
        import re, json
        clean = raw_text.replace("```json", "").replace("```", "").strip()

        # Tentativa 1: json.loads direto
        try:
            return json.loads(clean, strict=False)
        except Exception:
            pass

        # Tentativa 2: Extração por limites de objeto { ... }
        start_obj = clean.find("{")
        end_obj = clean.rfind("}")
        if start_obj != -1 and end_obj > start_obj:
            try:
                return json.loads(clean[start_obj:end_obj + 1], strict=False)
            except Exception:
                pass

        # Tentativa 3: Extração por limites de array [ ... ]
        start_arr = clean.find("[")
        end_arr = clean.rfind("]")
        if start_arr != -1 and end_arr > start_arr:
            try:
                return json.loads(clean[start_arr:end_arr + 1], strict=False)
            except Exception:
                pass

        # Tentativa 4: Limpeza de vírgulas sobressalentes e caracteres de controle
        sanitized = re.sub(r',(?=\s*[\}\]])', '', clean)
        sanitized = re.sub(r'[\r\n\t]+', ' ', sanitized)
        if start_obj != -1 and end_obj > start_obj:
            try:
                return json.loads(sanitized[start_obj:end_obj + 1], strict=False)
            except Exception:
                pass

        return None

    def _generate_json(self, prompt: str, temperature: float = 0.7):
        """Gera conteúdo estruturado em JSON usando response_mime_type='application/json' com fallback gracioso."""
        for m in self.fallback_models:
            try:
                response = self.client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=4096,
                        response_mime_type="application/json"
                    ),
                )
                self.model = m
                parsed = self._safe_parse_json(response.text or "")
                if parsed is not None:
                    return parsed
            except Exception as e:
                print(f"Modelo {m} falhou em _generate_json com response_mime_type: {e}")
                # Tentativa sem response_mime_type em caso de incompatibilidade do modelo
                try:
                    response = self.client.models.generate_content(
                        model=m,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=temperature,
                            max_output_tokens=4096
                        ),
                    )
                    self.model = m
                    parsed = self._safe_parse_json(response.text or "")
                    if parsed is not None:
                        return parsed
                except Exception as e2:
                    print(f"Modelo {m} falhou sem response_mime_type: {e2}")
                    continue
        return {}


    def _generate_with_search(self, prompt: str, temperature: float = 0.8) -> str:
        """Gera conteúdo ativando Google Search Grounding para obter informações dinâmicas e atualizadas da internet."""
        for m in self.fallback_models:
            try:
                response = self.client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=2048,
                        tools=[{"google_search": {}}]
                    ),
                )
                self.model = m
                return response.text or ""
            except Exception as e:
                print(f"Geração com busca no modelo {m} falhou: {e}. Tentando sem grounding...")
                try:
                    return self._generate(prompt, temperature=temperature)
                except Exception:
                    continue
        return self._generate(prompt, temperature=temperature)

    def _get_official_logo_b64(self) -> str:
        """Carrega e redimensiona a logomarca oficial do site visionai.com.br."""
        import os, io, base64
        from PIL import Image

        possible_paths = [
            os.path.join(os.path.dirname(__file__), "logo.png"),
            "/app/logo.png",
            "/home/hufema/vizionai/08_Governance_Corporate/Visionai_Corporate_Web/public/logo.png"
        ]

        for p in possible_paths:
            if os.path.exists(p):
                try:
                    img = Image.open(p)
                    img = img.resize((96, 96), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    return base64.b64encode(buf.getvalue()).decode("utf-8")
                except Exception as e:
                    print(f"Erro ao carregar logo de {p}: {e}")
                    continue
        return ""

    def _generate_svg_banner(self, title: str, category: str = "VisionAi Insights") -> str:
        """Gera um banner SVG corporativo 1200x630 com a logomarca e paleta oficial do site visionai.com.br (#9EFF00)."""
        import base64
        logo_b64 = self._get_official_logo_b64()
        logo_tag = f'<image href="data:image/png;base64,{logo_b64}" x="125" y="115" width="44" height="44"/>' if logo_b64 else '<rect x="125" y="115" width="44" height="44" rx="10" fill="url(#vision-grad)"/>'

        first_line = title.strip().split("\n")[0]
        clean_first_line = first_line.replace("#", "").replace("**", "").strip()
        clean_title = (clean_first_line[:75] + "...") if len(clean_first_line) > 75 else clean_first_line
        clean_category = category.upper()
        
        svg_code = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#050505"/>
      <stop offset="50%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#111111"/>
    </linearGradient>
    <linearGradient id="vision-grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#9EFF00"/>
      <stop offset="100%" stop-color="#0055FF"/>
    </linearGradient>
    <linearGradient id="card-bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="rgba(255,255,255,0.06)"/>
      <stop offset="100%" stop-color="rgba(255,255,255,0.02)"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="30" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
  </defs>

  <!-- Background corporativo oficial (#050505) -->
  <rect width="1200" height="630" fill="url(#bg)"/>
  
  <!-- Glows com tom verde oficial (#9EFF00) -->
  <circle cx="150" cy="120" r="180" fill="#9EFF00" opacity="0.12" filter="url(#glow)"/>
  <circle cx="1050" cy="500" r="220" fill="#0055FF" opacity="0.15" filter="url(#glow)"/>
  
  <!-- Linhas Guia da Computação Visual -->
  <path d="M 0 150 L 1200 150 M 0 300 L 1200 300 M 0 450 L 1200 450" stroke="rgba(158, 255, 0, 0.05)" stroke-width="1"/>
  <path d="M 300 0 L 300 630 M 600 0 L 600 630 M 900 0 L 900 630" stroke="rgba(158, 255, 0, 0.05)" stroke-width="1"/>

  <!-- Telemetria HUD retículo em Verde Neon (#9EFF00) -->
  <g opacity="0.7">
    <path d="M 980 160 L 1020 160 M 980 160 L 980 200" stroke="#9EFF00" stroke-width="2" fill="none"/>
    <path d="M 1120 160 L 1080 160 M 1120 160 L 1120 200" stroke="#9EFF00" stroke-width="2" fill="none"/>
    <rect x="980" y="140" width="140" height="18" fill="rgba(158, 255, 0, 0.2)" rx="2"/>
    <text x="985" y="153" font-family="'Inter', monospace" font-size="10" fill="#9EFF00" font-weight="700">AI DETECT: 99.8%</text>
  </g>

  <!-- Container de Vidro Glassmorphism -->
  <rect x="80" y="80" width="1040" height="470" rx="24" fill="url(#card-bg)" stroke="rgba(158,255,0,0.2)" stroke-width="1.5"/>
  
  <!-- Logo Oficial & Nome da Marca (VISION + AI em #9EFF00) -->
  <g transform="translate(130, 130)">
    {logo_tag}
    <text x="58" y="32" font-family="'Outfit', 'Inter', sans-serif" font-weight="900" font-size="26" fill="#ffffff" letter-spacing="-0.5">VISION<tspan fill="#9EFF00">AI</tspan></text>
    <text x="210" y="32" font-family="'Inter', sans-serif" font-weight="400" font-size="14" fill="#94a3b8">| Corporate Tech</text>
  </g>
  
  <!-- Selo de Categoria com Cores do Site -->
  <g transform="translate(900, 135)">
    <rect width="180" height="34" rx="17" fill="rgba(158, 255, 0, 0.12)" stroke="rgba(158, 255, 0, 0.45)" stroke-width="1.5"/>
    <text x="90" y="22" font-family="'Inter', sans-serif" font-weight="800" font-size="11" fill="#9EFF00" text-anchor="middle" letter-spacing="1">{clean_category}</text>
  </g>

  <!-- Título Principal em PT-BR -->
  <foreignObject x="130" y="210" width="940" height="220">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: 'Outfit', 'Inter', system-ui, sans-serif; color: #f8fafc; font-size: 40px; font-weight: 700; line-height: 1.25; letter-spacing: -1px; text-shadow: 0 4px 12px rgba(0,0,0,0.5);">
      {clean_title}
    </div>
  </foreignObject>

  <!-- Linha de Acento Verde-Azul -->
  <rect x="130" y="460" width="140" height="4" rx="2" fill="url(#vision-grad)"/>

  <!-- Rodapé Institucional do Site -->
  <text x="130" y="500" font-family="'Inter', sans-serif" font-weight="500" font-size="16" fill="#94a3b8">Inovação, Inteligência Artificial &amp; Computação na Borda</text>
  <text x="1070" y="500" font-family="'Inter', sans-serif" font-weight="800" font-size="15" fill="#9EFF00" text-anchor="end">visionai.com.br ✦</text>
</svg>"""
        return base64.b64encode(svg_code.encode('utf-8')).decode('utf-8')

    def get_auto_topics(self, category: str = None, force_refresh: bool = False) -> list:
        """Gera ou filtra tópicos B2B cobrindo as 6 linhas de serviço reais do site visionai.com.br."""
        import re as _re

        fallback_topics = [
            {"topic": "As câmeras que você já tem instaladas podem fiscalizar EPIs 24h/dia — sem nenhum humano olhando. Isso já é realidade com Edge AI", "category": "Visão Computacional", "format": "insight", "tone": "direto"},
            {"topic": "Fluxo invisível no armazém? Rastreamos 100% dos ativos, veículos e pessoas em tempo real — sem nova infraestrutura, só IA nas câmeras existentes", "category": "Visão Computacional", "format": "case", "tone": "tecnico"},
            {"topic": "Seu cliente envia foto + áudio + documento. Nossa IA analisa tudo em segundos com 95% de precisão. Isso é atendimento multimodal real", "category": "IA Multimodal", "format": "educativo", "tone": "tecnico"},
            {"topic": "URA que perde o fio quando o usuário muda de assunto? Criamos assistentes de voz com memória de contexto que executam ações em tempo real", "category": "IA Multimodal", "format": "provocativo", "tone": "provocativo"},
            {"topic": "No Meta Quest 3, simulamos cenários de risco real onde o erro não tem consequência — retenção 4x mais eficaz que treinamento convencional", "category": "EdTech & VR", "format": "case", "tone": "inspirador"},
            {"topic": "Como medir engajamento real em salas de aula e treinamentos corporativos com visão computacional ética e análise temporal em tempo real", "category": "EdTech & VR", "format": "storytelling", "tone": "visionario"},
            {"topic": "Perdas de safra por identificação tardia de pragas. Detectamos anomalias agrícolas dias antes de serem visíveis a olho nu — +15% produtividade, menos defensivos", "category": "Agro-Industrial", "format": "case", "tone": "inspirador"},
            {"topic": "Máquinas parando sem aviso em produção? Identificamos desgaste no hardware local, sem depender de nuvem. Manutenção preditiva onde não chega internet", "category": "Agro-Industrial", "format": "insight", "tone": "direto"},
            {"topic": "Produção de vídeo institucional: 3 semanas de trabalho → 2 dias com automação IA (roteiro, narração e edição automatizados)", "category": "Conteúdo & Mídia IA", "format": "storytelling", "tone": "visionario"},
            {"topic": "Propostas comerciais genéricas não fecham negócio. Geramos apresentações personalizadas por segmento de cliente de forma automática", "category": "Conteúdo & Mídia IA", "format": "lista", "tone": "direto"},
            {"topic": "Sua equipe gasta horas coletando dados de concorrentes manualmente? Automatizamos a inteligência competitiva com relatórios executivos em minutos", "category": "Governança & Intelligence", "format": "lista", "tone": "provocativo"},
            {"topic": "Portais corporativos orientados a conversão B2B: construímos ecossistemas digitais de alta credibilidade para decisores C-Level", "category": "Governança & Intelligence", "format": "insight", "tone": "educativo"},
        ]

        topics_list = []
        if force_refresh:
            site_content = self.scraped_context or ""
            cat_prompt = f" com foco exclusivo na categoria '{category}'" if category else ""
            prompt = f"""
Você é um estrategista de conteúdo LinkedIn B2B para a empresa VisionAI (https://visionai.com.br).

INFORMAÇÕES DA EMPRESA:
{ORG_CONTEXT}

CONTEÚDO REAL DO SITE:
{site_content[:2000]}

Gere EXATAMENTE 12 ideias de posts B2B{cat_prompt}, distribuídos entre as 6 linhas de serviço da VisionAI:
1. Visão Computacional (Câmeras existentes, EPIs, Rastreamento, Edge AI)
2. IA Multimodal (OmniVoice, Voz+Vídeo+Texto, URA Cognitiva)
3. EdTech & VR (Realidade Mista, Meta Quest 3, Engajamento Educacional)
4. Agro-Industrial (Drones, Manutenção Preditiva Offline, Detecção Pragas)
5. Conteúdo & Mídia IA (Vídeos Corporativos, Apresentações Automatizadas)
6. Governança & Intelligence (Portais Executivos, Análise Competitiva)

REGRAS:
- NUNCA mencionar SAP
- Responda APENAS JSON válido sem markdown:
[{"topic": "...", "category": "Visão Computacional|IA Multimodal|EdTech & VR|Agro-Industrial|Conteúdo & Mídia IA|Governança & Intelligence", "format": "insight|case|storytelling|lista", "tone": "direto|tecnico|provocativo|visionario"}]
"""
            try:
                raw = self._generate(prompt, temperature=0.85)
                json_match = _re.search(r'\[.*?\]', raw, _re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    if isinstance(parsed, list) and len(parsed) > 0:
                        topics_list = parsed
            except Exception as e:
                print(f"Aviso ao gerar tópicos via Gemini: {e}")

        if not topics_list:
            topics_list = fallback_topics

        if category:
            cat_lower = category.lower()
            filtered = [t for t in topics_list if cat_lower in t.get("category", "").lower()]
            return filtered if filtered else topics_list

        return topics_list

    def _composite_advertising_creative(self, raw_img_bytes: bytes, pt_headline: str, category: str = "VisionAi Insights", overlay_style: str = "photo_pure") -> tuple[str, str]:
        """
        Combina a foto realista gerada por IA de acordo com o estilo visual escolhido pelo usuário:
        - photo_pure: Foto 100% pura sem molduras nem overlays (Zero interferência de logo ou marca)
        - editorial_magazine: Foto editorial estilo Forbes/HBR com badge minimalista
        - ad_banner: Banner publicitário completo com marca VisionAI e rodapé
        """
        import base64
        if overlay_style == "photo_pure":
            img_b64 = base64.b64encode(raw_img_bytes).decode('utf-8')
            print("Foto editorial pura 100% sem moldura nem logo gerada com sucesso!")
            return img_b64, "image/jpeg"

        import io, html
        from PIL import Image
        import cairosvg

        try:
            bg = Image.open(io.BytesIO(raw_img_bytes)).convert("RGB")
            bg = bg.resize((1200, 630), Image.Resampling.LANCZOS)
            logo_b64 = self._get_official_logo_b64()

            dna = self._get_dynamic_brand_dna()
            company_name = html.escape(dna['company_name'])
            company_name_upper = html.escape(dna['company_name'].upper())
            website_url_clean = html.escape(dna['website_url'].replace('https://', '').replace('http://', '').rstrip('/'))
            industry_clean = html.escape(dna['industry'][:55])

            first_line = pt_headline.strip().split("\n")[0]
            clean_first_line = first_line.replace("#", "").replace("**", "").strip()
            clean_category = html.escape(category.upper())

            if overlay_style == "editorial_magazine":
                # Estilo Revista Editorial Minimalista (Forbes / Harvard Business Review)
                logo_tag = f'<image href="data:image/png;base64,{logo_b64}" x="55" y="45" width="28" height="28"/>' if logo_b64 else ''
                svg_overlay = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="bottom-shadow" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%" stop-color="rgba(0,0,0,0.80)"/>
      <stop offset="45%" stop-color="rgba(0,0,0,0.30)"/>
      <stop offset="100%" stop-color="rgba(0,0,0,0.0)"/>
    </linearGradient>
  </defs>

  <!-- Gradiente suave inferior apenas no rodapé -->
  <rect y="280" width="1200" height="350" fill="url(#bottom-shadow)"/>

  <!-- Badge Minimalista no Topo Esquerdo -->
  <g transform="translate(50, 40)">
    <rect width="210" height="36" rx="8" fill="rgba(15, 23, 42, 0.85)" stroke="rgba(255,255,255,0.2)" stroke-width="1"/>
    {logo_tag}
    <text x="{48 if logo_b64 else 16}" y="23" font-family="'Inter', sans-serif" font-weight="700" font-size="11" fill="#ffffff" letter-spacing="1">{company_name_upper} EDITORIAL</text>
  </g>

  <!-- Badge de Categoria no Topo Direito -->
  <g transform="translate(940, 40)">
    <rect width="200" height="36" rx="8" fill="rgba(15, 23, 42, 0.85)" stroke="rgba(158, 255, 0, 0.5)" stroke-width="1"/>
    <text x="100" y="23" font-family="'Inter', sans-serif" font-weight="700" font-size="11" fill="#9EFF00" text-anchor="middle" letter-spacing="1">{clean_category}</text>
  </g>

  <!-- Manchete Minimalista -->
  <text x="50" y="550" font-family="'Outfit', 'Inter', sans-serif" font-size="34" fill="#ffffff" font-weight="800">
    {html.escape(clean_first_line[:65])}
  </text>
</svg>"""
            else:
                # Banner Publicitário Oficial (ad_banner)
                logo_tag = f'<image href="data:image/png;base64,{logo_b64}" x="80" y="55" width="44" height="44"/>' if logo_b64 else '<rect x="80" y="55" width="44" height="44" rx="10" fill="url(#vision-grad)"/>'
                
                def wrap_text_to_tspans(text: str, max_chars: int = 42, start_x: int = 80, dy: int = 48) -> str:
                    words = text.strip().replace('#', '').replace('*', '').split()
                    lines, current_line, current_len = [], [], 0
                    for word in words:
                        if current_len + len(word) + 1 > max_chars and current_line:
                            lines.append(" ".join(current_line))
                            current_line = [word]
                            current_len = len(word)
                        else:
                            current_line.append(word)
                            current_len += len(word) + 1
                    if current_line:
                        lines.append(" ".join(current_line))
                    tspans = []
                    for i, l in enumerate(lines[:4]):
                        d = 0 if i == 0 else dy
                        tspans.append(f'<tspan x="{start_x}" dy="{d}">{html.escape(l)}</tspan>')
                    return "\n".join(tspans)

                headline_tspans = wrap_text_to_tspans(clean_first_line)

                svg_overlay = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <defs>
    <linearGradient id="vision-grad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#9EFF00"/>
      <stop offset="100%" stop-color="#0055FF"/>
    </linearGradient>
    <linearGradient id="shadow" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%" stop-color="rgba(5,5,5,0.92)"/>
      <stop offset="60%" stop-color="rgba(5,5,5,0.55)"/>
      <stop offset="100%" stop-color="rgba(5,5,5,0.20)"/>
    </linearGradient>
  </defs>

  <rect width="1200" height="630" fill="url(#shadow)"/>

  <g transform="translate(80, 55)">
    {logo_tag}
    <text x="54" y="32" font-family="'Outfit', 'Inter', sans-serif" font-weight="900" font-size="26" fill="#ffffff" letter-spacing="-0.5">{company_name}</text>
  </g>

  <g transform="translate(920, 58)">
    <rect width="200" height="36" rx="18" fill="rgba(158, 255, 0, 0.12)" stroke="rgba(158, 255, 0, 0.45)" stroke-width="1.5"/>
    <text x="100" y="23" font-family="'Inter', sans-serif" font-weight="800" font-size="12" fill="#9EFF00" text-anchor="middle" letter-spacing="1">{clean_category}</text>
  </g>

  <text x="80" y="220" font-family="'Outfit', 'Inter', sans-serif" font-size="38" fill="#ffffff" font-weight="800">
    {headline_tspans}
  </text>

  <rect x="80" y="535" width="140" height="4" rx="2" fill="url(#vision-grad)"/>
  <text x="80" y="575" font-family="'Inter', sans-serif" font-weight="500" font-size="14" fill="#94a3b8">{industry_clean}</text>
  <text x="1120" y="575" font-family="'Inter', sans-serif" font-weight="800" font-size="15" fill="#9EFF00" text-anchor="end">{website_url_clean} ✦</text>
</svg>"""

            overlay_png = cairosvg.svg2png(bytestring=svg_overlay.encode('utf-8'))
            overlay_img = Image.open(io.BytesIO(overlay_png)).convert('RGBA')

            composite = Image.alpha_composite(bg.convert('RGBA'), overlay_img)
            out = io.BytesIO()
            composite.convert('RGB').save(out, format='JPEG', quality=95)
            
            img_b64 = base64.b64encode(out.getvalue()).decode('utf-8')
            return img_b64, "image/jpeg"
        except Exception as e:
            print(f"Erro ao compor peça publicitária: {e} — usando foto original")
            img_b64 = base64.b64encode(raw_img_bytes).decode('utf-8')
            return img_b64, "image/jpeg"

    def _generate_image_base64(self, prompt: str, pt_title: str = "VisionAI Insights", category: str = "VisionAi Insights", overlay_style: str = "photo_pure") -> tuple[str, str]:
        """Gera uma imagem realista ou artística pura via Gemini Image Models e compõe de acordo com o overlay_style escolhido."""
        clean_prompt = prompt.replace("\n", " ").strip()
        negative_rules = ", NO text, NO written words, NO letters, NO signs, NO typography, 8k resolution, highly detailed, masterwork"
        full_prompt = clean_prompt + negative_rules if "NO text" not in clean_prompt else clean_prompt

        # Modelos ativos para geração nativa de imagem no SDK google-genai
        image_models = ["gemini-2.5-flash-image", "gemini-3.1-flash-image", "gemini-3.1-flash-image-preview"]

        for model in image_models:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        temperature=0.7,
                    )
                )
                if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if part.inline_data and part.inline_data.data:
                            img_bytes = part.inline_data.data
                            print(f"Arte visual gerada com sucesso via modelo {model} ({len(img_bytes)} bytes)!")
                            return self._composite_advertising_creative(img_bytes, pt_headline=pt_title, category=category, overlay_style=overlay_style)
            except Exception as e:
                print(f"Modelo de imagem {model} falhou: {e}")
                continue

        # Fallback: SVG corporativo VisionAI com título em Português (PT-BR)
        print("Usando banner SVG corporativo como fallback visual com título em Português.")
        svg_b64 = self._generate_svg_banner(title=pt_title)
        return svg_b64, "image/svg+xml"

    def _clean_post_content(self, text: str) -> tuple[str, str]:
        """
        Remove cercas markdown (```markdown), preâmbulos conversacionais da IA, rótulos de títulos (ex: '1. TITLE:')
        e limpa asteriscos markdown (**bold**, *italic*, # Header) incompatíveis com a publicação nativa do LinkedIn.
        Retorna (texto_limpo_completo, titulo_manchete_limpo).
        """
        import re
        if not text:
            return ("", "VisionAI Insights")
        
        # 1. Remove cercas de código ```markdown
        cleaned = re.sub(r"^```(?:markdown|text|json)?\s*", "", text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())

        # 2. Limpeza rigorosa de marcações Markdown incompatíveis com LinkedIn (asteriscos **, *, hashes #)
        # Converte negritos markdown **texto** -> texto (remove os asteriscos brutos)
        cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
        # Converte itálicos ou asteriscos avulsos *texto* -> texto
        cleaned = re.sub(r"\*(.*?)\*", r"\1", cleaned)
        # Converte títulos markdown (# Título -> Título)
        cleaned = re.sub(r"^[#]+\s*(.+)$", r"\1", cleaned, flags=re.MULTILINE)
        # Substitui tópicos marcados com asterisco/trífen no início da linha por emojis elegantes
        cleaned = re.sub(r"^\*\s+", "▸ ", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^\-\s+", "▸ ", cleaned, flags=re.MULTILINE)

        lines = [l.strip() for l in cleaned.split("\n") if l.strip()]
        
        # 3. Filtra preâmbulos conversacionais, sugestões de banner entre colchetes ou prefixos de prompt nas primeiras linhas
        meta_patterns = [
            r"^aqui está", r"^segue ", r"^com base ", r"^conforme ", r"^proposta de post",
            r"^olá", r"^prezado", r"^\d+\.\s*title:", r"^title:", r"^título:", r"^post:", r"^assunto:", r"^prompt:",
            r"^\[sugestão", r"^\[imagem", r"^\[banner", r"^\[foto", r"^\[note", r"^\[nota"
        ]
        
        while lines:
            first_line = lines[0].lower()
            is_meta = False
            if lines[0].startswith("[") and lines[0].endswith("]"):
                is_meta = True
            else:
                for pat in meta_patterns:
                    if re.search(pat, first_line):
                        is_meta = True
                        break
            if is_meta:
                lines.pop(0)
            else:
                break
                
        clean_full_text = "\n\n".join(lines)
        # 4. Encontra a melhor manchete em português para a faixa do criativo
        clean_headline = "VisionAI Insights"
        for line in lines:
            clean_l = re.sub(r"^[\#\*\d\.\-\s]+", "", line).strip()
            clean_l = re.sub(r"^(?:hook|desafio|solução|insight|paradigm shift|pilar \d+):\s*", "", clean_l, flags=re.IGNORECASE).strip()
            if len(clean_l) >= 12 and not clean_l.endswith(":"):
                clean_headline = clean_l
                break
                
        return (clean_full_text, clean_headline)

    def regenerate_media_from_revised_text(
        self,
        revised_text: str,
        media_type: str = "image",
        overlay_style: str = "photo_pure",
        art_style: str = "auto",
        topic: str = "",
        tone: str = "",
        content_objective: str = ""
    ) -> dict:
        """
        Gera uma peça visual aplicando ESTRITAMENTE as parametrizações e guardrails escolhidos pelo usuário no formulário.
        """
        clean_full_text, fallback_headline = self._clean_post_content(revised_text)

        art_style_directives = {
            "auto": "LIVRE: Escolha a melhor expressão artística adaptada ao conteúdo (Render 3D Abstrato, Fotografia Editorial, Ilustração Minimalista ou Frame Cinematográfico).",
            "photo": "FOTOGRAFIA EDITORIAL REALISTA: Capa de revista (Forbes, Wired, NatGeo). PROIBIDO usar vetores ou ilustrações 3D.",
            "render_3d": "RENDER 3D ABSTRATO E CONCEITUAL: Estilo Cinema4D / Octane Render com geometrias flutuantes, redes de dados 3D e iluminação volumétrica. PROIBIDO fotos de pessoas em escritórios!",
            "illustration": "ILUSTRAÇÃO MINIMALISTA E VETORIAL: Estilo revista New Yorker ou Tech Review, vetores limpos e design gráfico contemporâneo. PROIBIDO fotografias!",
            "cinematic": "FRAME CINEMATOGRÁFICO WIDESCREEN (16:9): Iluminação dramática de filme/documentário, alto contraste e storytelling visual marcante.",
            "infographic": "DIAGRAMA E INFOGRÁFICO TÉCNICO DIDÁTICO: Esquema visual limpo representando arquiteturas, conexões de dados ou conceitos."
        }

        selected_art_directive = art_style_directives.get(art_style, art_style_directives["auto"])

        prompt = f"""
Você é um Diretor de Arte Internacional e Fotógrafo Editorial de Elite.

PARAMETRIZAÇÕES E GUARDRAILS ESTRITOS DEFINIDOS PELO USUÁRIO (MANDATÓRIOS):
- TEMA / TÍTULO DA CRIAÇÃO: {topic or 'Extraído do texto'}
- OBJETIVO DO CONTEÚDO: {'🎓 EDUCATIVO & CIENTÍFICO (Foco em dados, papers e ensino puro - SEM PITCH DE VENDAS)' if content_objective == 'educativo_academic' else '🚀 CORPORATIVO & PITCH B2B'}
- TOM DE VOZ: {tone or 'Livre'}
- ESTILO ARTÍSTICO OBRIGATÓRIO DA IMAGEM (`art_style`): {selected_art_directive}

TEXTO REVISADO DO POST NO LINKEDIN:
---
{clean_full_text[:2000]}
---

REGRAS RÍGIDAS E INVIOLÁVEIS DE CUMPRIMENTO DAS PARAMETRIZAÇÕES (GUARDRAILS):
1. **RESPEITE RIGOROSAMENTE O ESTILO ARTÍSTICO SELECIONADO (`art_style`)**:
   - Se o estilo for 'render_3d', O PROMPT DEVE SER PARA UMA ARTE 3D ABSTRATA (Cinema4D / Octane Render). PROIBIDO foto de pessoas de terno ou escritórios!
   - Se o estilo for 'illustration', O PROMPT DEVE SER PARA UMA ILUSTRAÇÃO VETORIAL MINIMALISTA. PROIBIDO fotografias reais!
   - Se o estilo for 'cinematic', O PROMPT DEVE SER PARA UM FRAME CINEMATOGRÁFICO DRAMÁTICO.
   - Se o estilo for 'infographic', O PROMPT DEVE SER PARA UM DIAGRAMA VISUAL TÉCNICO E LIMPO.
   - Se o estilo for 'photo', O PROMPT DEVE SER PARA FOTOGRAFIA EDITORIAL DE ALTA RESOLUÇÃO.

2. **RESPEITE O CONTEÚDO ESPECÍFICO DO TEXTO**:
   - Analise o assunto exato, a metáfora, o setor e a história do post.
   - NUNCA repita o mesmo padrão genérico de 'mesa de escritório corporativa com tablet e pessoas de terno' a menos que o post trate especificamente de reuniões corporativas!

3. **FORMATO DE SAÍDA**:
   - Descreva a cena em INGLÊS com detalhes de iluminação, paleta de cores, composição e assunto.
   - ADICIONE NO FINAL DO PROMPT: 'masterpiece, highly detailed, 8k resolution, crisp focus, NO text, NO written words, NO letters, NO typography, NO logos'.

Responda APENAS com JSON:
{{
  "category": "NOME_CURTO_DA_CATEGORIA_EM_PT",
  "clickbait_headline": "Manchete Provocativa em Português",
  "image_prompt": "prompt de imagem em inglês respeitando estritamente o guardrail"
}}
"""
        raw = self._generate(prompt, temperature=0.85)
        import re
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        image_prompt = ""
        category_name = "VISIONAI INSIGHTS"
        clickbait_headline = ""
        if json_match:
            try:
                data = json.loads(json_match.group())
                image_prompt = data.get("image_prompt", "")
                category_name = data.get("category", "VISIONAI INSIGHTS")
                clickbait_headline = data.get("clickbait_headline", "").strip()
            except Exception:
                pass
        
        if not image_prompt:
            image_prompt = f"Creative visual concept representing: {clean_full_text[:100]}"
            
        final_banner_title = clickbait_headline if (clickbait_headline and len(clickbait_headline) >= 10) else fallback_headline
        img_b64, mime = self._generate_image_base64(image_prompt, pt_title=final_banner_title, category=category_name, overlay_style=overlay_style)
        return {
            "category": category_name,
            "creative_headline": final_banner_title,
            "image_prompt": image_prompt,
            "image_base64": img_b64,
            "image_mime": mime,
            "media_type": media_type
        }

    # ── 1. GERAÇÃO DE POSTS ────────────────────────────────────────────────────
    def generate_post(
        self,
        topic: str,
        format_type: str = "standard",
        tone: str = "visionario",
        media_type: str = "image",
        voice_mode: str = "corporate",
        content_objective: str = "corporativo_sales",
        web_research: bool = False,
        overlay_style: str = "photo_pure",
        art_style: str = "auto",
        source_url: str = ""
    ) -> dict:
        """Gera um post completo com texto e mídia respeitando rigorosamente a leitura do PDF/paper na íntegra, objetivo e estéticas."""
        
        format_guides = {
            "pulse_article": (
                "Artigo Estratégico LinkedIn Pulse / Essay Didático (400-600 palavras) — Estrutura completa de autoridade e liderança de pensamento:\n"
                "1. TÍTULO EXECUTIVO MANCHETE: Título impactante\n"
                "2. INTRODUÇÃO E HOOK: Contextualização histórica e definição clara da tecnologia/tema.\n"
                "3. DESENVOLVIMENTO TÉCNICO / PILARES: Explicação aprofundada dos conceitos, algoritmos, arquiteturas ou artigos da área.\n"
                "4. DADOS & IMPACTO NO MERCADO: Métricas reais, estudos de caso e benchmarks de mercado.\n"
                "5. TENDÊNCIAS FUTURAS & CONCLUSÃO: Visão de futuro e fechamento de alto valor."
            ),
            "strategic_framework": (
                "Framework Executivo & Manifesto (250-400 palavras) — Modelo conceitual estruturado em passos práticos e arquitetura conceitual."
            ),
            "case": (
                "Estudo de Caso & Análise de Resultados (200-350 palavras) — Focado em problemas reais, solução aplicada e métricas de impacto."
            ),
            "storytelling": (
                "Storytelling Corporativo & Bastidores (200-300 palavras) — Narrativa envolvente sobre descobertas, aprendizados e conquistas."
            ),
            "insight": (
                "Insight Provocativo C-Level (150-250 palavras) — Provocação conceitual de alto impacto desafiando dogmas do mercado."
            ),
            "standard": (
                "Post B2B Padrão + Banner (150-250 palavras) — Conteúdo objetivo e direto ao ponto com gancho poderoso e fechamento claro."
            )
        }

        tone_guides = {
            "visionario": "Tom visionário e autoritativo — questione o status quo com pragmatismo executivo, provoque reflexão profunda no C-level",
            "tecnico": "Tom analítico, arquitetural e científico — cite fundamentos de algoritmos, latência, métricas e ROI mensurável",
            "inspirador": "Tom focado em transformação de negócios, avanço científico e impacto real na sociedade",
            "educativo": "Tom consultivo e pedagógico de alta liderança, ensinando o mercado com profundidade e clareza conceitual",
            "provocativo": "Tom provocativo C-Level — desafie dogmas tradicionais e questione a inércia corporativa com urgência",
            "direto": "Tom direto, objetivo e pragmático — direto ao ponto, focado em ação e dados concretos",
            "storytelling": "Tom narrativo de liderança — conte uma jornada profissional real, descobertas e lições aprendidas",
            "persuasivo": "Tom publicitário e altamente persuasivo — focado em conversão B2B de alto valor e diferenciais tecnológicos"
        }

        voice_instruction = (
            "PERFIL DE VOZ INSTITUCIONAL: Escreva com autoridade corporativa institucional de referência no setor."
            if voice_mode == "corporate" else
            "PERFIL DE VOZ FOUNDER / THOUGHT LEADERSHIP: Escreva em 1ª PESSOA ('Eu', 'Nossa equipe de P&D', 'Analisando este artigo científico...'). Conte uma perspectiva profissional autêntica."
        )

        # Configuração do Objetivo (Educativo/Papers vs Corporativo/Vendas)
        if content_objective == "educativo_academic":
            objective_directive = (
                "MODO: CONTEÚDO EDUCATIVO, CIENTÍFICO & THOUGHT LEADERSHIP (PESQUISA & PAPERS Acadêmicos).\n"
                "Sua missão é EDUCAR E ENSINAR O LEITOR de forma extremamente enriquecedora, didática e cientificamente embasada.\n"
                "REGRAS RÍGIDAS DO MODO EDUCATIVO:\n"
                "- Explique o conceito de forma neutra, completa e magistral (história, algoritmos, definições, aplicações).\n"
                "- CITE pesquisas, papers acadêmicos, avanços recentes e benchmarks do mercado de IA.\n"
                "- PROIBIDO forçar discursos de vendas comerciais da empresa ou citar câmeras de fábrica/NR-12 a menos que o tema seja especificamente sobre isso.\n"
                "- Termine com uma pergunta instigante para debate intelectual nos comentários do LinkedIn."
            )
            org_context_block = ""
        else:
            objective_directive = (
                "MODO: COMUNICAÇÃO CORPORATIVA, MARKETING B2B & SOLUÇÕES INSTITUCIONAIS.\n"
                "Sua missão é conectar o tema às soluções estratégicas, ROI e diferenciais competitivos da empresa."
            )
            org_context_block = f"CONTEXTO INSTITUCIONAL:\n{self._get_brand_dna_context()}\n{self.scraped_context}\n"

        # Leitura INTEGRAL do Paper / Artigo se houver URL ou fonte especificada
        import re
        paper_full_content = ""
        target_link = source_url.strip() if source_url else ""
        if not target_link:
            url_match = re.search(r'https?://[^\s]+', topic)
            if url_match:
                target_link = url_match.group(0)

        if target_link:
            paper_full_content = self._fetch_full_paper_or_url_content(target_link)

        paper_context_block = ""
        if paper_full_content:
            paper_context_block = f"""
CONTEÚDO COMPLETO EXTRAÍDO E LIDO NA ÍNTEGRA DO PAPER/ARTIGO FONTE ({target_link}):
{paper_full_content[:18000]}

INSTRUÇÃO CRÍTICA DO AGENTE DE IA:
- Você LEU O PAPER COMPLETO ACIMA. Analise detalhadamente as hipóteses, metodologias, equações/arquiteturas e resultados empíricos descritos.
- Escreva o post 100% em PORTUGUÊS DO BRASIL (PT-BR) com base na leitura detalhada deste artigo.
"""

        # ── ETAPA 1: GERAÇÃO DO TEXTO DO POST ──────────────────────────────────
        text_prompt = f"""
Você é um especialista em Inteligência Artificial, Pesquisador de TI e Redator de Alto Nível para o LinkedIn.

{objective_directive}

{org_context_block}

{paper_context_block}

PERFIL DE NARRATIVA: {voice_instruction}
TEMA/TÍTULO SOLICITADO: {topic}
FORMATO DE CONTEÚDO: {format_guides.get(format_type, format_guides['standard'])}
TOM DE VOZ: {tone_guides.get(tone, tone_guides['visionario'])}

DIRETRIZES DE COPYWRITING & FORMATAÇÃO (ESTRITAMENTE OBRIGATÓRIAS):
1. **IDIOMA E LEITURA DO PAPER**:
   - Todo o texto deve ser escrito OBRIGATORIAMENTE em PORTUGUÊS DO BRASIL (PT-BR).
   - Se um paper ou documento foi lido acima, incorpore os conceitos e fundamentos desse estudo.

2. **RESPEITE O FORMATO E O OBJETIVO SOLICITADO**:
   - Se o formato for 'pulse_article', crie um artigo completo com seções organizadas, introdução conceitual e aprofundamento.
   - Se o modo for 'educativo_academic', NÃO insira pitches comerciais da empresa. Foque em entregar conhecimento puro e valioso.

3. **ZERO ASTERISCOS OU MARKDOWN**:
   - PROIBIDO usar asteriscos (`**` ou `*`) para negrito ou itálico (o LinkedIn exibe os asteriscos brutos no feed).
   - PROIBIDO usar cerquilhas (`#`, `##`) como títulos.
   - Use emojis elegantes (como `✦`, `▸`, `⚡`, `💡`, `👉`, `📍`) para destacar pontos e títulos.

4. **ESTILO DE ESCRITA HUMANO E RICO**:
   - PROIBIDO clichês robóticos de IA como: "No mundo de hoje", "Em constante evolução", "Na era da IA", "Em suma", "Vamos juntos".
   - Parágrafos curtos (2 a 3 linhas) para excelente leitura no celular.

FORMATO DE SAÍDA: Retorne APENAS o texto do post em Português do Brasil (PT-BR), pronto para ser publicado. Sem explicações adicionais e SEM NENHUM ASTERISCO.
"""
        # Se a pesquisa na web estiver ativada ou for modo educativo, usa Google Search Grounding para trazer artigos e dados recentes!
        if web_research or content_objective == "educativo_academic":
            search_prompt = f"Pesquise na web artigos científicos, papers recentes em Português do Brasil (PT-BR) sobre: '{topic}'. {text_prompt}"
            raw_post_text = self._generate_with_search(search_prompt, temperature=0.85).strip()
        else:
            raw_post_text = self._generate(text_prompt, temperature=0.85).strip()

        post_text, _ = self._clean_post_content(raw_post_text)

        # ── ETAPA 2: GERAÇÃO DA ARTE VISUAL BASEADA NO TEXTO CRIADO ──────────────
        art_result = self.regenerate_media_from_revised_text(
            post_text,
            media_type=media_type,
            overlay_style=overlay_style,
            art_style=art_style,
            topic=topic,
            tone=tone,
            content_objective=content_objective
        )
        
        image_prompt = art_result.get("image_prompt", "")
        image_b64 = art_result.get("image_base64", "")
        image_mime = art_result.get("image_mime", "image/svg+xml")

        return {
            "topic": topic,
            "format": format_type,
            "tone": tone,
            "content": post_text,
            "category": art_result.get("category"),
            "creative_headline": art_result.get("creative_headline"),
            "image_prompt": image_prompt,
            "image_base64": image_b64,
            "image_mime": image_mime,
            "media_type": media_type,
            "char_count": len(post_text),
            "model": self.model,
            "image_model": IMAGE_MODEL if image_b64 else None
        }

    # ── 2. REVISÃO E MELHORIA DE POST ─────────────────────────────────────────
    def review_post(self, draft: str) -> dict:
        """Analisa e melhora um rascunho de post."""
        prompt = f"""
Você é um especialista em LinkedIn Marketing da VisionAi.

CONTEXTO DA EMPRESA:
{ORG_CONTEXT}

RASCUNHO DO POST:
{draft}

TAREFA: Analise este post e forneça:
1. PONTUAÇÃO (0-10) com justificativa breve
2. PONTOS FORTES (lista de 2-3 itens)
3. MELHORIAS SUGERIDAS (lista de 2-3 itens)
4. VERSÃO MELHORADA (reescreva o post aplicando as melhorias)

Responda em JSON com as chaves: "score", "strengths", "improvements", "improved_version"
"""
        raw = self._generate(prompt, temperature=0.5)
        try:
            # Tenta extrair JSON do texto
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {"raw": raw, "model": self.model}

    # ── 3. ANÁLISE DE ANALYTICS ───────────────────────────────────────────────
    def analyze_analytics(self, analytics_data: dict) -> str:
        """Interpreta dados de analytics e gera insights executivos."""
        prompt = f"""
Você é analista sênior de marketing da VisionAi.

CONTEXTO DA EMPRESA:
{ORG_CONTEXT}

DADOS DE ANALYTICS DO LINKEDIN (últimos 12 meses):
{json.dumps(analytics_data, ensure_ascii=False, indent=2)}

TAREFA: Gere um relatório executivo em Português com:
1. **Resumo Executivo** (2-3 frases sobre a performance geral)
2. **Métricas-Chave** (destaque os números mais importantes)
3. **Tendências Identificadas** (o que está crescendo, o que está caindo)
4. **Diagnóstico** (por que esses resultados estão acontecendo)
5. **Recomendações Estratégicas** (3 ações concretas para melhorar)
6. **Próximos Passos** (o que fazer nas próximas 2 semanas)

Use markdown para formatação. Seja direto e orientado a dados.
"""
        return self._generate(prompt, temperature=0.4)

    # ── 4. ANÁLISE DE SEGUIDORES ──────────────────────────────────────────────
    def analyze_followers(self, follower_data: dict) -> str:
        """Gera insights sobre o perfil demográfico dos seguidores."""
        prompt = f"""
Você é estrategista de audiência da VisionAi.

CONTEXTO DA EMPRESA:
{ORG_CONTEXT}

DADOS DE SEGUIDORES:
{json.dumps(follower_data, ensure_ascii=False, indent=2)}

TAREFA: Analise o perfil dos seguidores e responda em Português:
1. **Quem está seguindo a VisionAi** (perfil dominante)
2. **Alinhamento com ICP** (Ideal Customer Profile — está alinhado com o público-alvo?)
3. **Oportunidades** (segmentos que podemos explorar mais)
4. **Gaps** (quem deveria seguir mas não está)
5. **Sugestões de conteúdo** baseadas no perfil da audiência

Use markdown. Seja específico e acionável.
"""
        return self._generate(prompt, temperature=0.5)

    # ── 5. ESTRATÉGIA DE CONTEÚDO ─────────────────────────────────────────────
    def generate_content_strategy(self, kpis: dict, period_days: int = 30) -> dict:
        """Gera um calendário editorial e estratégia de conteúdo."""
        prompt = f"""
Você é o Head de Marketing de Conteúdo da VisionAi.

CONTEXTO DA EMPRESA:
{ORG_CONTEXT}

KPIs ACTUAIS:
{json.dumps(kpis, ensure_ascii=False, indent=2)}

TAREFA: Crie uma estratégia de conteúdo para os próximos {period_days} dias.

Retorne um JSON com a seguinte estrutura:
{{
  "strategy_summary": "resumo da estratégia em 2-3 frases",
  "posting_frequency": "recomendação de frequência",
  "best_times": ["lista de melhores horários para postar"],
  "content_pillars": [
    {{"pillar": "nome do pilar", "percentage": 30, "rationale": "justificativa"}}
  ],
  "post_ideas": [
    {{"week": 1, "topic": "tema", "format": "formato", "hook": "gancho sugerido"}}
  ],
  "hashtag_strategy": ["hashtags recomendadas para a conta"],
  "kpi_targets": {{"followers_growth": "meta", "impressions": "meta", "engagement_rate": "meta"}}
}}

Gere ideias de posts para 4 semanas (2-3 posts por semana). Responda APENAS com o JSON.
"""
        raw = self._generate(prompt, temperature=0.7)
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return {"raw": raw, "model": self.model}

    # ── 6. INSIGHTS DO DASHBOARD ──────────────────────────────────────────────
    def generate_dashboard_insight(self, summary: dict) -> str:
        """Gera comentário executivo rápido para o dashboard."""
        prompt = f"""
Você é um CMO assistente da VisionAi. Em 2-3 frases directas e impactantes,
comente o estado actual do LinkedIn corporativo com base nestes dados:

{json.dumps(summary, ensure_ascii=False)}

Tom: executivo, directo, sem floreados. Use números. Indique 1 prioridade imediata.
Responda em Português do Brasil.
"""
        return self._generate(prompt, temperature=0.4)

    # ── 7. ANÁLISE DE POST INDIVIDUAL ─────────────────────────────────────────
    def analyze_single_post(self, post_content: str, post_metrics: dict = None) -> str:
        """Analisa performance e qualidade de um post específico."""
        metrics_section = ""
        if post_metrics:
            metrics_section = f"\nMÉTRICAS DO POST:\n{json.dumps(post_metrics, ensure_ascii=False)}\n"

        prompt = f"""
Analise este post do LinkedIn da VisionAi:

CONTEÚDO:
{post_content}
{metrics_section}
Forneça em Português:
- O que funcionou bem neste post
- O que poderia ser melhorado
- Como adaptar este conteúdo para gerar mais engajamento
- Sugestão de um post de seguimento (follow-up) sobre o mesmo tema

Use markdown. Seja específico e prático.
"""
        return self._generate(prompt, temperature=0.5)

    # ── 8. GERAÇÃO DE HASHTAGS ────────────────────────────────────────────────
    def generate_hashtags(self, topic: str, count: int = 8) -> list:
        """Gera hashtags optimizadas para um tópico específico."""
        prompt = f"""
Gere {count} hashtags do LinkedIn para um post da VisionAi sobre: "{topic}"

Contexto: {ORG_CONTEXT}

Misture hashtags em português e inglês. Inclua:
- 2-3 hashtags de alto volume (ex: #IA, #Tecnologia)
- 3-4 hashtags de nicho (mais específicas ao tema)
- 1-2 hashtags de marca ou sectorial

Retorne APENAS uma lista JSON de strings. Ex: ["#IA", "#TransformacaoDigital"]
"""
        raw = self._generate(prompt, temperature=0.6)
        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
        except Exception:
            pass
        return []

    def _parse_trends_json(self, raw_text: str) -> list:
        """Extrai objetos de tendência de forma resiliente mesmo com falhas de sintaxe JSON do LLM."""
        if not raw_text:
            return []
            
        clean = raw_text.replace("```json", "").replace("```", "").strip()
        
        # Tentativa 1: json.loads com strict=False
        start = clean.find("{")
        end = clean.rfind("}") + 1
        if start != -1 and end > start:
            try:
                res = json.loads(clean[start:end], strict=False)
                if isinstance(res, dict) and "trends" in res and isinstance(res["trends"], list):
                    return res["trends"]
            except Exception as e:
                print(f"json.loads com strict=False falhou: {e}")

        # Tentativa 2: Parse via Regex dos campos individualmente
        import re
        title_m = re.findall(r'"title"\s*:\s*"([^"]+)"', clean)
        cat_m = re.findall(r'"category"\s*:\s*"([^"]+)"', clean)
        sum_m = re.findall(r'"summary"\s*:\s*"([^"]+)"', clean)
        imp_m = re.findall(r'"impact_b2b"\s*:\s*"([^"]+)"', clean)
        top_m = re.findall(r'"suggested_topic"\s*:\s*"([^"]+)"', clean)
        
        trends = []
        for i in range(len(title_m)):
            trends.append({
                "title": title_m[i].strip(),
                "category": cat_m[i].strip().upper() if i < len(cat_m) else "INOVAÇÃO B2B",
                "summary": sum_m[i].strip() if i < len(sum_m) else title_m[i].strip(),
                "impact_b2b": imp_m[i].strip() if i < len(imp_m) else "Impacto estratégico para operações B2B.",
                "suggested_topic": top_m[i].strip() if i < len(top_m) else title_m[i].strip()
            })
            
        return trends

    # ── 9. RADAR DE TENDÊNCIAS DA WEB (DINÂMICO + PERSISTÊNCIA EM DB + EXCLUSÃO DE USADOS) ───────
    def fetch_web_trends(self, query: str = None, force_refresh: bool = False) -> dict:
        """Busca notícias e tendências em tempo real na web cobrindo os pilares estratégicos da VisionAI.
           Salva no banco SQLite, ordena de forma aleatória a cada requisição e oculta automaticamente matérias usadas (used = True).
        """
        from database import init_db, SessionLocal, WebTrendItem
        from sqlalchemy.sql.expression import func
        import random, time, re, json

        init_db()
        db = SessionLocal()

        try:
            # 1. Se não for varredura forçada e houver itens suficientes no banco, retorna uma amostragem ALEATÓRIA
            if not force_refresh and not query:
                q = db.query(WebTrendItem).filter(WebTrendItem.used == False)
                cached_items = q.order_by(func.random()).limit(12).all()
                if len(cached_items) >= 12:
                    return {
                        "trends": [
                            {
                                "id": item.id,
                                "title": item.title,
                                "category": item.category,
                                "summary": item.summary,
                                "impact_b2b": item.impact_b2b,
                                "suggested_topic": item.suggested_topic,
                                "used": item.used
                            }
                            for item in cached_items
                        ]
                    }

            # 2. Varredura dinâmica em tempo real na internet via Gemini + Google Search Grounding
            sectors_pool = [
                "Visão Computacional e Inspeção de Qualidade em Fábricas com Edge AI",
                "Drones com Visão Preditiva e Sensores em Agrobusiness de Larga Escala",
                "Realidade Mista, Meta Quest 3 e Treinamento Imersivo em EdTech Corporativa",
                "SAC Multimodal com IA de Voz Humanizada e Atendimento ao Cliente",
                "Governança C-Level, Inteligência de Mercado e Radar de Concorrência",
                "Automação Generativa de Mídia, Marketing B2B e Geração de Conteúdo",
                "Robótica Industrial, Câmeras Inteligentes e Prevenção de Acidentes NR-12",
                "Processamento Local em Borda (Edge Computing) sem Dependência da Nuvem",
                "Inovações de IA Generativa para VPs de Operações e Engenharia",
                "Tendências de Tecnologia B2B no Brasil e na América Latina neste mês"
            ]

            chosen_sectors = random.sample(sectors_pool, min(3, len(sectors_pool)))
            if query:
                chosen_sectors.insert(0, query)

            search_query_str = " e ".join(chosen_sectors)
            timestamp_seed = int(time.time())

            prompt = f"""
Você é o Diretor de Inteligência de Mercado & Tendências Tecnológicas B2B da VisionAI (visionai.com.br).

SUA MISSÃO: Realize uma busca em tempo real na internet (Google Search) e traga exatamente de 8 a 12 notícias e tendências B2B RECENTES, REAIS E INÉDITAS sobre:
{search_query_str} (Data/Seed: {timestamp_seed}).

REGRA RÍGIDA DE IDIOMA (ESTRITAMENTE OBRIGATÓRIO):
- TODAS AS NOTÍCIAS, TÍTULOS, RESUMOS E IMPACTOS B2B DEVEM SER RETORNADOS 100% EM PORTUGUÊS DO BRASIL (PT-BR).
- Se a fonte original ou o portal for em inglês ou outro idioma, traduza e adapte perfeitamente para o Português do Brasil.

Responda APENAS com um objeto JSON válido (sem qualquer bloco de código markdown como ```json):
{{
  "trends": [
    {{
      "title": "Título específico em Português do Brasil",
      "category": "EDGE AI | VISÃO AGRO | REALIDADE MISTA | GOVERNANÇA | SAC MULTIMODAL | SEGURANÇA | ROBÓTICA | MÍDIA B2B",
      "summary": "Resumo executivo de 2 a 3 frases em Português do Brasil",
      "impact_b2b": "Por que isso importa para diretores e VPs B2B (em PT-BR)",
      "suggested_topic": "Tema estratégico em Português do Brasil para post no LinkedIn"
    }}
  ]
}}
"""
            raw = self._generate_with_search(prompt, temperature=0.95)
            parsed_trends = self._parse_trends_json(raw)

            # Fallback dinâmico via Gemini sem grounding se o parse da busca falhou
            if not parsed_trends:
                try:
                    fallback_prompt = f"Gere 6 notícias B2B inéditas e variadas sobre {search_query_str}. Responda em JSON com a chave 'trends' contendo objetos com 'title', 'category', 'summary', 'impact_b2b', 'suggested_topic'."
                    raw_fb = self._generate(fallback_prompt, temperature=0.95)
                    parsed_trends = self._parse_trends_json(raw_fb)
                except Exception as err_fb:
                    print(f"Erro no fallback dinâmico de tendências: {err_fb}")

            # 3. Grava no banco de dados SQLite (evitando duplicatas pelo título)
            for t in parsed_trends:
                title = t.get("title", "").strip()
                if not title:
                    continue
                exists = db.query(WebTrendItem).filter(WebTrendItem.title == title).first()
                if not exists:
                    trend_obj = WebTrendItem(
                        title=title,
                        category=t.get("category", "INOVAÇÃO B2B").upper(),
                        summary=t.get("summary", ""),
                        impact_b2b=t.get("impact_b2b", ""),
                        suggested_topic=t.get("suggested_topic", title),
                        used=False
                    )
                    db.add(trend_obj)
            db.commit()

            # 4. Retorna matérias não usadas do banco ordenadas aleatoriamente
            q_active = db.query(WebTrendItem).filter(WebTrendItem.used == False)
            if query:
                q_active = q_active.filter(WebTrendItem.title.ilike(f"%{query}%") | WebTrendItem.summary.ilike(f"%{query}%") | WebTrendItem.category.ilike(f"%{query}%"))

            active_items = q_active.order_by(func.random()).limit(12).all()
            if active_items:
                return {
                    "trends": [
                        {
                            "id": item.id,
                            "title": item.title,
                            "category": item.category,
                            "summary": item.summary,
                            "impact_b2b": item.impact_b2b,
                            "suggested_topic": item.suggested_topic,
                            "used": item.used
                        }
                        for item in active_items
                    ]
                }
        except Exception as e:
            print(f"Erro em fetch_web_trends: {e}")
        finally:
            db.close()

        return {"trends": []}

    def mark_trend_used(self, trend_id: int = None, topic: str = None) -> bool:
        """Marca uma tendência como usada (used = True) no banco de dados SQLite para ocultá-la de futuras listagens."""
        from database import SessionLocal, WebTrendItem
        db = SessionLocal()
        try:
            item = None
            if trend_id:
                item = db.query(WebTrendItem).filter(WebTrendItem.id == trend_id).first()
            if not item and topic:
                snippet = topic.strip()[:20]
                item = db.query(WebTrendItem).filter(
                    (WebTrendItem.suggested_topic.ilike(f"%{snippet}%")) | 
                    (WebTrendItem.title.ilike(f"%{snippet}%"))
                ).first()
                
            if item:
                item.used = True
                db.commit()
                print(f"Tendência ID {item.id} ('{item.title}') marcada como USADA (used=True).")
                return True
        except Exception as e:
            print(f"Erro ao marcar tendência como usada: {e}")
        finally:
            db.close()
        return False

    # ── 10. GERADOR DE CARROSSÉIS PDF PARA LINKEDIN ─────────────────────────────
    def generate_carousel_pdf(
        self,
        topic: str,
        slide_count: int = 5,
        tone: str = "provocativo",
        content_objective: str = "lideranca_pensamento",
        art_style: str = "tech_modern",
        overlay_style: str = "cyberpunk_neon",
        target_audience: str = "",
        web_research: bool = False,
        source_url: str = ""
    ) -> dict:
        """Gera um roteiro em slides e compõe um arquivo PDF multi-slide corporativo obedecendo ao tom, objetivo, marca e regras do criativo."""
        import io, base64, html, json, re
        import cairosvg
        from pypdf import PdfWriter, PdfReader

        dna = self._get_dynamic_brand_dna()
        brand_name = dna.get("company_name", "VisionAI")
        website_url = dna.get("website_url", "https://visionai.com.br")
        company_industry = dna.get("industry", "Inteligência Artificial & Computação de Borda")
        default_target = dna.get("target_audience", "C-Levels, Diretores de TI, Heads de Operações")
        effective_audience = target_audience.strip() if target_audience else default_target

        tone_instructions = {
            "provocativo": "Use manchetes provocativas e desafiadoras que questionem o status quo e provoquem ação imediata.",
            "executivo": "Use tom estritamente executivo B2B, focado em ROI, eficiência financeira, métricas corporativas e governança.",
            "tecnico": "Use terminologia técnica precisa, arquitetura de sistemas, benchmarks reais e detalhes operacionais de engenharia.",
            "educativo": "Use tom didático e explicativo passo a passo, desmistificando conceitos complexos e ensinando boas práticas.",
            "urgente": "Use tom de alerta e urgência máxima, destacando riscos iminentes de segurança, perda de mercado e não conformidade."
        }.get(tone, f"Use um tom de voz {tone}.")

        objective_instructions = {
            "lideranca_pensamento": "Posicione a empresa como líder absoluta e autoridade técnica no setor.",
            "educativo_academic": "Baseie a explicação em dados empíricos, pesquisas, papers e evidências científicas.",
            "case_sucesso": "Estruture o carrossel em formato de Estudo de Caso (Desafio → Solução → Resultados Medidos).",
            "vendas_diretas": "Conduza cada slide para um forte Call to Action de demonstração comercial."
        }.get(content_objective, f"Foque no objetivo de {content_objective}.")

        target_link = source_url.strip() if source_url else ""
        if not target_link:
            url_match = re.search(r'https?://[^\s]+', topic)
            if url_match:
                target_link = url_match.group(0)

        paper_full_text = ""
        if target_link:
            paper_full_text = self._fetch_full_paper_or_url_content(target_link)

        research_context = ""
        if paper_full_text:
            research_context = f"\n📄 CONTEÚDO EXTRAÍDO DO PAPER/ARTIGO FONTE ({target_link}):\n{paper_full_text[:4000]}\n\nIMPORTANTE: Crie os slides em PORTUGUÊS DO BRASIL fundamentados nos achados e descobertas do artigo acima.\n"
        else:
            # Varredura ativa na internet via Google Search Grounding para o tema solicitado
            query = f"{topic}".strip()
            web_data = self.fetch_web_trends(query=query, force_refresh=True)
            if web_data and web_data.get("trends"):
                t_list = web_data["trends"][:4]
                research_context = "\n🌐 PESQUISAS E DADOS EM TEMPO REAL EXTRAÍDOS DA WEB (PT-BR):\n" + "\n".join([f"• {t.get('title')}: {t.get('summary')}" for t in t_list]) + "\n"

        prompt = f"""
Você é um Estrategista Executivo de Conteúdo e Designer de Apresentações B2B de classe mundial da empresa {brand_name} ({website_url}).
Setor: {company_industry}

Sua missão é criar o roteiro em exatamente {slide_count} slides para um Carrossel Infográfico Corporativo no LinkedIn sobre o tema: "{topic}".

PÚBLICO-ALVO: {effective_audience}
TOM DE VOZ: {tone.upper()} ({tone_instructions})
OBJETIVO: {content_objective.upper()} ({objective_instructions})
{research_context}

ORIENTAÇÕES DE CRIAÇÃO FLUIDA & CONTEÚDO NATURAL:
- NÃO utilize uma estrutura rígida ou repetitiva. Desenvolva os {slide_count} slides de forma orgânica, fluida, didática e de alto valor em PORTUGUÊS DO BRASIL (PT-BR).
- Cada slide deve revelar um conceito, dado, arquitetura, mito vs realidade, estudo de caso ou diretriz prática extraída das pesquisas ou do tema.
- O campo "badge" deve ser uma etiqueta dinâmica em caixa alta perfeitamente alinhada com o conteúdo exato do slide (ex: "DEFINIÇÃO", "DESAFIO DE ROI", "ARQUITETURA EDGE", "DADOS DE MERCADO", "MITO vs REALIDADE", "ESTUDO DE CASO", "CHECKLIST", "AÇÃO PRÁTICA").
- O campo "headline" deve conter uma manchete direta e magnética (6 a 12 palavras).
- O campo "body" deve conter uma explicação pragmática de alto valor (15 a 35 palavras).

Responda APENAS com um objeto JSON no formato:
{{
  "title": "Título Impactante do Carrossel sobre {topic}",
  "slides": [
    {{
      "slide_number": 1,
      "badge": "BADGE DINÂMICO EM CAIXA ALTA",
      "headline": "Manchete Principal do Slide 1",
      "body": "Texto rico e explicativo fundamentado no tema"
    }}
  ]
}}
"""
        data = self._generate_json(prompt, temperature=0.7)
        slides_data = []
        carousel_title = topic

        if isinstance(data, dict):
            slides_data = data.get("slides", [])
            carousel_title = data.get("title", topic)

        if not slides_data or not isinstance(slides_data, list):
            slides_data = []
            fallback_stages = [
                ("CAPA & VISÃO", f"{topic[:50]}", f"Como liderar a transformação e obter vantagem competitiva em {topic}."),
                ("O DESAFIO", f"O Desafio em {topic[:35]}", f"Entenda as barreiras operacionais, riscos e custos ocultos enfrentados em {topic}."),
                ("A VIRADA DE CHAVE", f"Estratégia para {topic[:35]}", f"Abordagem tecnológica e arquitetura ideal desenvolvida para {effective_audience}."),
                ("MÉTRICAS & ROI", "Resultados Mensuráveis", f"Impacto direto de {topic} com ganhos de eficiência, redução de falhas e ROI medido."),
                ("PRÓXIMOS PASSOS", "Transformação Contínua", f"Acesse {website_url} e consulte nossos especialistas em {topic}.")
            ]
            for idx in range(slide_count):
                stage_idx = min(idx, len(fallback_stages) - 1)
                badge, h_text, b_text = fallback_stages[stage_idx]
                if idx >= len(fallback_stages):
                    badge = f"SLIDE {idx+1}"
                    h_text = f"Aprofundando {topic[:35]}"
                    b_text = f"Análise detalhada de implementação e melhores práticas de {topic} para {effective_audience}."
                slides_data.append({
                    "slide_number": idx + 1,
                    "badge": badge,
                    "headline": h_text,
                    "body": b_text
                })


        logo_b64 = self._get_official_logo_b64()
        logo_tag = f'<image href="data:image/png;base64,{logo_b64}" x="80" y="70" width="50" height="50"/>' if logo_b64 else '<rect x="80" y="70" width="50" height="50" rx="12" fill="url(#vision-grad)"/>'

        # Definição de Cores e Estilo Visual baseados em overlay_style e art_style
        if overlay_style == "cyberpunk_neon":
            bg_color_1 = "#050505"
            bg_color_2 = "#0f172a"
            accent_color = "#9EFF00"
            secondary_accent = "#00E5FF"
            badge_bg = "rgba(158,255,0,0.15)"
            badge_border = "rgba(158,255,0,0.5)"
            badge_text = "#9EFF00"
        elif overlay_style == "minimalist":
            bg_color_1 = "#0f172a"
            bg_color_2 = "#1e293b"
            accent_color = "#00E5FF"
            secondary_accent = "#ffffff"
            badge_bg = "rgba(255,255,255,0.1)"
            badge_border = "rgba(255,255,255,0.3)"
            badge_text = "#ffffff"
        elif overlay_style == "glassmorphism":
            bg_color_1 = "#0b1329"
            bg_color_2 = "#172554"
            accent_color = "#38BDF8"
            secondary_accent = "#818CF8"
            badge_bg = "rgba(56,189,248,0.15)"
            badge_border = "rgba(56,189,248,0.4)"
            badge_text = "#38BDF8"
        elif overlay_style == "executive_frame":
            bg_color_1 = "#0B192C"
            bg_color_2 = "#1E3E62"
            accent_color = "#F59E0B"
            secondary_accent = "#00E5FF"
            badge_bg = "rgba(245,158,11,0.15)"
            badge_border = "rgba(245,158,11,0.5)"
            badge_text = "#F59E0B"
        else:
            bg_color_1 = "#050505"
            bg_color_2 = "#0f172a"
            accent_color = "#9EFF00"
            secondary_accent = "#00E5FF"
            badge_bg = "rgba(158,255,0,0.15)"
            badge_border = "rgba(158,255,0,0.5)"
            badge_text = "#9EFF00"

        writer = PdfWriter()
        total_slides = len(slides_data)

        for s in slides_data:
            s_num = s.get("slide_number", 1)
            badge = html.escape(str(s.get("badge", brand_name)).upper())
            headline = html.escape(str(s.get("headline", "")))
            body = html.escape(str(s.get("body", "")))

            def wrap_svg_text(txt: str, max_chars: int = 24, start_x: int = 80, start_y: int = 420, dy: int = 70, font_size: int = 56, fill_color: str = "#ffffff") -> str:
                words = txt.split()
                lines = []
                curr = []
                c_len = 0
                for w in words:
                    if c_len + len(w) + 1 > max_chars and curr:
                        lines.append(" ".join(curr))
                        curr = [w]
                        c_len = len(w)
                    else:
                        curr.append(w)
                        c_len += len(w) + 1
                if curr:
                    lines.append(" ".join(curr))
                
                tspans = []
                for i, line in enumerate(lines[:4]):
                    y_pos = start_y + (i * dy)
                    tspans.append(f'<text x="{start_x}" y="{y_pos}" font-family="\'Outfit\', \'Inter\', sans-serif" font-weight="800" font-size="{font_size}" fill="{fill_color}">{line}</text>')
                return "\n".join(tspans)

            headline_svg = wrap_svg_text(headline, max_chars=22, start_x=80, start_y=380, dy=68, font_size=54, fill_color="#ffffff")
            body_svg = wrap_svg_text(body, max_chars=38, start_x=80, start_y=720, dy=42, font_size=28, fill_color="#94a3b8")

            svg_slide = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">
  <defs>
    <linearGradient id="bg-grad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{bg_color_1}"/>
      <stop offset="50%" stop-color="{bg_color_2}"/>
      <stop offset="100%" stop-color="{bg_color_1}"/>
    </linearGradient>
    <linearGradient id="vision-grad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{accent_color}"/>
      <stop offset="100%" stop-color="{secondary_accent}"/>
    </linearGradient>
  </defs>

  <rect width="1080" height="1080" fill="url(#bg-grad)"/>
  <circle cx="950" cy="150" r="300" fill="{accent_color}" opacity="0.08"/>
  <circle cx="150" cy="950" r="350" fill="{secondary_accent}" opacity="0.10"/>

  <g transform="translate(80, 70)">
    {logo_tag}
    <text x="64" y="36" font-family="'Outfit', sans-serif" font-weight="900" font-size="28" fill="#ffffff">{html.escape(brand_name.upper())}</text>
    <text x="260" y="36" font-family="'Inter', sans-serif" font-weight="400" font-size="16" fill="#94a3b8">| {html.escape(tone.capitalize())} B2B</text>
  </g>

  <g transform="translate(740, 75)">
    <rect width="260" height="42" rx="21" fill="{badge_bg}" stroke="{badge_border}" stroke-width="1.5"/>
    <text x="130" y="27" font-family="'Inter', sans-serif" font-weight="800" font-size="13" fill="{badge_text}" text-anchor="middle" letter-spacing="1">{badge}</text>
  </g>

  {headline_svg}
  <rect x="80" y="650" width="160" height="6" rx="3" fill="url(#vision-grad)"/>
  {body_svg}

  <g transform="translate(80, 980)">
    <text x="0" y="0" font-family="'Inter', sans-serif" font-weight="600" font-size="18" fill="#64748b">✦ {html.escape(website_url.replace('https://','').replace('http://',''))}</text>
    <text x="920" y="0" font-family="'Inter', sans-serif" font-weight="800" font-size="18" fill="{accent_color}" text-anchor="end">Slide {s_num}/{total_slides}</text>
  </g>
</svg>"""

            pdf_page_bytes = cairosvg.svg2pdf(bytestring=svg_slide.encode('utf-8'))
            reader = PdfReader(io.BytesIO(pdf_page_bytes))
            writer.add_page(reader.pages[0])

        out_pdf_buf = io.BytesIO()
        writer.write(out_pdf_buf)
        pdf_bytes = out_pdf_buf.getvalue()
        pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')

        return {
            "title": carousel_title,
            "slides_count": total_slides,
            "pdf_base64": pdf_b64,
            "pdf_mime": "application/pdf"
        }

    # ── 11. EXTRAÇÃO & TRANSFORMAÇÃO DE DOCUMENTOS ─────────────────────────────
    def parse_document_to_posts(self, document_text: str) -> dict:
        """Converte o conteúdo textual de um documento/PDF interno em uma série de 3 a 5 posts B2B."""
        prompt = f"""
Você é o Diretor de Conteúdo B2B da VisionAI (visionai.com.br).

DOCUMENTO INTERNO FORNECIDO:
---
{document_text[:4000]}
---

SUA TAREFA:
Analise este documento corporativo e desmembre-o em 3 posts de alto impacto para o LinkedIn.

Responda APENAS com JSON:
{{
  "document_summary": "Resumo executivo do documento em 2 frases",
  "generated_posts": [
    {{
      "post_number": 1,
      "topic": "Tema central do post",
      "angle": "Ângulo (ex: ROI, Estudo de Caso, Provocação)",
      "content": "Texto completo do post em Português com hashtags"
    }}
  ]
}}
"""
        raw = self._generate(prompt, temperature=0.7)
        import re, json
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            try:
                res = json.loads(json_match.group())
                for post in res.get("generated_posts", []):
                    if post.get("content"):
                        clean_text, _ = self._clean_post_content(post["content"])
                        post["content"] = clean_text
                return res
            except Exception as e:
                print(f"Erro no parse_document_to_posts: {e}")
        return {"document_summary": "Documento processado com sucesso", "generated_posts": []}
