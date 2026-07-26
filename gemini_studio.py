import os
import json
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

MODEL = "gemini-3.1-flash-image"

ORG_CONTEXT = """
Empresa: VisionAi | Inovação, IA & Transformação Digital
LinkedIn: linkedin.com/company/visionaicombr
Segmento: Consultoria de IA, SAP, Cloud, EdTech para mercado corporativo LATAM
Tom de voz: Autoritativo, visionário, técnico com foco em ROI, desafiador do hype
Idioma: Português do Brasil (informal-profissional)
Público-alvo: C-Levels, Diretores de TI, Heads de Inovação, PMs Sênior
Pilares de conteúdo: IA Generativa, Soberania de Dados, Transformação Digital, SAP S/4HANA, EdTech Corporativo
"""

class GeminiStudio:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_KEY") or ""
        self.client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})
        self.model = MODEL
        self.fallback_models = ["gemini-3.1-flash-image", "gemini-3.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        self.scraped_context = self._scrape_visionai_website()

    def _scrape_visionai_website(self) -> str:
        """Scrapes the VisionAI website to get the latest context for creatives."""
        try:
            response = requests.get("https://visionai.com.br", timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                text = soup.get_text(separator=" ", strip=True)
                # Keep first 2000 characters to avoid huge contexts
                return f"\n\nCONTEÚDO DO SITE OFICIAL:\n{text[:2000]}"
        except Exception as e:
            print(f"Erro ao fazer scraping do site: {e}")
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
                err_str = str(e)
                if "404" in err_str or "NOT_FOUND" in err_str or "model" in err_str.lower():
                    continue  # tenta próximo modelo da lista
                return f"[Erro Gemini: {err_str}]"
        return f"[Erro Gemini: Nenhum modelo disponível para a chave configurada]"

    # ── 1. GERAÇÃO DE POSTS ────────────────────────────────────────────────────
    def generate_post(self, topic: str, format_type: str = "standard", tone: str = "visionario") -> dict:
        """Gera um post completo para o LinkedIn corporativo."""
        format_guides = {
            "standard": "Post de texto direto, 150-300 palavras, 3-5 hashtags relevantes.",
            "storytelling": "Post narrativo com gancho inicial forte, história de transformação, CTA claro. 200-400 palavras.",
            "lista": "Post em formato de lista numerada (5-7 itens), título impactante, conclusão forte.",
            "insight": "Post de insight provocativo, dado/estatística de abertura, análise profunda, chamada à reflexão.",
            "case": "Post sobre caso de uso ou resultado, antes/depois, números reais (use exemplos plausíveis), CTA.",
            "poll_idea": "Sugira um poll de 4 opções sobre o tema, com contexto de introdução para o LinkedIn.",
        }

        tone_guides = {
            "visionario": "Tom visionário e desafiador — questione o status quo, provoque reflexão",
            "tecnico": "Tom técnico com profundidade, cite frameworks, metodologias e métricas",
            "inspirador": "Tom inspirador e motivacional, focado em transformação e impacto humano",
            "educativo": "Tom educativo e didático, explique conceitos complexos de forma acessível",
        }

        prompt = f"""
Você é o redator sênior de LinkedIn da VisionAi e diretor de arte.

CONTEXTO DA EMPRESA:
{ORG_CONTEXT}
{self.scraped_context}

TAREFA: Crie um "Criativo Completo" para um post de LinkedIn sobre o seguinte tema:
TEMA: {topic}
FORMATO: {format_guides.get(format_type, format_guides['standard'])}
TOM: {tone_guides.get(tone, tone_guides['visionario'])}

REGRAS DO POST:
- Primeira linha deve ser um gancho poderoso
- Use emojis estrategicamente (máximo 5)
- Hashtags no final (3-5, relevantes e em português/inglês)
- Foque em valor real e insights acionáveis
- Termine com uma pergunta ou CTA que gere engajamento

REGRAS DO CRIATIVO (IMAGEM):
- Você DEVE sugerir um prompt visual hiper-detalhado (em inglês) para gerar a arte que acompanhará o post.
- Descreva a iluminação, estilo (ex: fotorealista, vetor, 3D render, cyberpunk, corporativo limpo), cores principais e elementos visuais.

FORMATO DE SAÍDA OBRIGATÓRIO:
Retorne APENAS um JSON válido contendo as chaves:
"post_text": "o texto do post aqui",
"image_prompt": "o prompt em inglês para o gerador de imagem aqui"
"""
        content = self._generate(prompt, temperature=0.85)
        return {
            "topic": topic,
            "format": format_type,
            "tone": tone,
            "content": content,
            "char_count": len(content),
            "model": self.model,
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
        return [t.strip() for t in raw.split(",") if "#" in t]
