import os
import requests
import json
from datetime import datetime
from typing import Optional

LI_API_VERSION = "202503"
LI_BASE = "https://api.linkedin.com"


class LinkedInCorporate:
    """
    Cliente LinkedIn API focado exclusivamente na App Corporativa Vizionai.
    Org ID: 106355456 | App: 77ow1venbjuuqo
    Scopes: r_basicprofile, r_1st_connections_size, r_member_postAnalytics,
            r_member_profileAnalytics, r_organization_followers,
            r_organization_social, r_organization_social_feed,
            rw_organization_admin, w_member_social, w_member_social_feed,
            w_organization_social, w_organization_social_feed
    """

    def __init__(self):
        self.token = (os.getenv("LINKEDIN_ACCESS_TOKEN") or "").strip()
        self.org_id = os.getenv("LINKEDIN_ORG_ID", "106355456")
        self.org_urn = f"urn:li:organization:{self.org_id}"
        self.person_urn = os.getenv("LINKEDIN_PERSON_URN", "urn:li:person:7y8dp014B6")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "LinkedIn-Version": LI_API_VERSION,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict = None) -> dict:
        try:
            url = f"{LI_BASE}{path}"
            r = requests.get(url, headers=self.headers, params=params, timeout=15)
            if r.status_code == 200:
                return {"ok": True, "data": r.json()}
            return {"ok": False, "status": r.status_code, "error": r.text}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _post(self, path: str, payload: dict) -> dict:
        try:
            url = f"{LI_BASE}{path}"
            r = requests.post(url, headers=self.headers, json=payload, timeout=15)
            if r.status_code in [200, 201]:
                post_id = r.headers.get("x-restli-id") or r.headers.get("X-RestLi-Id")
                body = {}
                try:
                    body = r.json()
                except Exception:
                    pass
                return {"ok": True, "id": post_id, "data": body}
            return {"ok": False, "status": r.status_code, "error": r.text}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _delete(self, path: str) -> dict:
        try:
            url = f"{LI_BASE}{path}"
            r = requests.delete(url, headers=self.headers, timeout=15)
            if r.status_code in [200, 204]:
                return {"ok": True}
            return {"ok": False, "status": r.status_code, "error": r.text}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ─── r_basicprofile ───────────────────────────────────────────────────────
    def get_me(self) -> dict:
        """Perfil básico do utilizador autenticado."""
        return self._get("/v2/me")

    # ─── r_organization_followers ─────────────────────────────────────────────
    def get_follower_count(self) -> dict:
        """Número total de seguidores da organização."""
        return self._get(
            f"/v2/networkSizes/{self.org_urn}",
            params={"edgeType": "CompanyFollowedByMember"},
        )

    # ─── r_organization_social ────────────────────────────────────────────────
    def get_follower_statistics(self) -> dict:
        """Breakdown de seguidores por indústria, seniority, função, etc."""
        return self._get(
            "/v2/organizationalEntityFollowerStatistics",
            params={"q": "organizationalEntity", "organizationalEntity": self.org_urn},
        )

    # ─── r_organization_social_feed ───────────────────────────────────────────
    def get_share_statistics(self, start_ms: int, end_ms: int, granularity: str = "MONTH") -> dict:
        """Analytics de posts: impressões, engagement, shares por período."""
        return self._get(
            "/v2/organizationalEntityShareStatistics",
            params={
                "q": "organizationalEntity",
                "organizationalEntity": self.org_urn,
                "timeIntervals.timeGranularityType": granularity,
                "timeIntervals.timeRange.start": start_ms,
                "timeIntervals.timeRange.end": end_ms,
            },
        )

    def get_share_statistics_last_12m(self) -> dict:
        """Últimos 12 meses de analytics de posts."""
        now = int(datetime.utcnow().timestamp() * 1000)
        # 12 meses ≈ 365 dias em ms (limite da API: max 13 meses)
        start = now - (365 * 24 * 60 * 60 * 1000)
        return self.get_share_statistics(start, now, "MONTH")

    # ─── w_organization_social + w_organization_social_feed ───────────────────
    def create_org_post(self, text: str, visibility: str = "PUBLIC") -> dict:
        """Publica um post na página da organização Vizionai."""
        payload = {
            "author": self.org_urn,
            "commentary": text,
            "visibility": visibility,
            "distribution": {"feedDistribution": "MAIN_FEED"},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        return self._post("/rest/posts", payload)

    def create_org_post_draft(self, text: str) -> dict:
        """Cria rascunho de post da organização (não publicado)."""
        payload = {
            "author": self.org_urn,
            "commentary": text,
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED"},
            "lifecycleState": "DRAFT",
            "isReshareDisabledByAuthor": False,
        }
        return self._post("/rest/posts", payload)

    def delete_org_post(self, post_urn: str) -> dict:
        """Apaga um post da organização."""
        encoded = post_urn.replace(":", "%3A")
        return self._delete(f"/rest/posts/{encoded}")

    def _upload_image(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
        """
        Faz upload de uma imagem para o LinkedIn e retorna o imageUrn.
        Fluxo: initializeUpload → PUT bytes → retorna urn
        """
        import base64 as b64_mod

        # Step 1: Initialize upload
        init_payload = {
            "initializeUploadRequest": {
                "owner": self.org_urn,
            }
        }
        init_headers = {**self.headers, "Content-Type": "application/json"}
        init_url = f"{LI_BASE}/rest/images?action=initializeUpload"
        try:
            r = requests.post(init_url, headers=init_headers, json=init_payload, timeout=15)
            if r.status_code not in [200, 201]:
                return {"ok": False, "error": f"initializeUpload failed: {r.status_code} {r.text}"}
            data = r.json().get("value", {})
            upload_url = data.get("uploadUrl")
            image_urn = data.get("image")
            if not upload_url or not image_urn:
                return {"ok": False, "error": f"Missing uploadUrl or imageUrn: {data}"}
        except Exception as e:
            return {"ok": False, "error": f"initializeUpload exception: {e}"}

        # Step 2: PUT the image bytes
        try:
            put_headers = {"Authorization": f"Bearer {self.token}", "Content-Type": mime_type}
            r2 = requests.put(upload_url, headers=put_headers, data=image_bytes, timeout=30)
            if r2.status_code not in [200, 201, 204]:
                return {"ok": False, "error": f"Image PUT failed: {r2.status_code} {r2.text}"}
        except Exception as e:
            return {"ok": False, "error": f"Image PUT exception: {e}"}

        return {"ok": True, "image_urn": image_urn}

    def create_org_post_with_image(
        self,
        text: str,
        image_b64: str,
        image_mime: str = "image/jpeg",
        alt_text: str = "VisionAI — Enxergando o Futuro com Inteligência",
        visibility: str = "PUBLIC",
    ) -> dict:
        """
        Publica um post com imagem na página da organização VisionAI.
        Aceita imagem em base64. Se SVG, publica só texto.
        """
        import base64 as b64_mod

        # SVG não é suportado como imagem LinkedIn — publica só texto
        if image_mime == "image/svg+xml" or not image_b64:
            return self.create_org_post(text, visibility)

        # Decodifica bytes da imagem
        try:
            img_bytes = b64_mod.b64decode(image_b64)
        except Exception as e:
            return {"ok": False, "error": f"Base64 decode failed: {e}"}

        # Faz upload da imagem
        upload_result = self._upload_image(img_bytes, image_mime)
        if not upload_result.get("ok"):
            # Fallback: publica só texto
            print(f"Upload de imagem falhou ({upload_result.get('error')}). Publicando só texto.")
            return self.create_org_post(text, visibility)

        image_urn = upload_result["image_urn"]

        # Cria post com imagem
        payload = {
            "author": self.org_urn,
            "commentary": text,
            "visibility": visibility,
            "distribution": {"feedDistribution": "MAIN_FEED"},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
            "content": {
                "media": {
                    "altText": alt_text,
                    "id": image_urn,
                }
            },
        }
        return self._post("/rest/posts", payload)

    # ─── rw_organization_admin ────────────────────────────────────────────────
    def get_org_admins(self) -> dict:
        """Lista administradores da organização."""
        return self._get(
            "/v2/organizationAcls",
            params={
                "q": "roleAssignee",
                "role": "ADMINISTRATOR",
                "projection": "(elements*(organization~(id,localizedName,vanityName,logoV2),roleAssignee~(id,firstName,lastName)))",
            },
        )

    def get_org_info(self) -> dict:
        """Detalhes da organização (nome, bio, website, etc.)."""
        return self._get(
            f"/v2/organizations/{self.org_id}",
            params={
                "projection": "(id,localizedName,vanityName,description,websiteUrl,staffCountRange,specialities,logoV2)"
            },
        )

    # ─── r_1st_connections_size ───────────────────────────────────────────────
    def get_network_size(self) -> dict:
        """Tamanho da rede pessoal do utilizador autenticado."""
        return self._get(
            f"/v2/networkSizes/{self.person_urn}",
            params={"edgeType": "CompanyFollowedByMember"},
        )

    # ─── r_member_profileAnalytics ────────────────────────────────────────────
    def get_profile_views(self) -> dict:
        """Visualizações do perfil pessoal (últimos 30 dias)."""
        now = int(datetime.utcnow().timestamp() * 1000)
        start = now - (30 * 24 * 60 * 60 * 1000)
        return self._get(
            "/v2/memberNetworkProfileAnalytics",
            params={
                "q": "member",
                "member": self.person_urn,
                "timeIntervals.timeGranularityType": "DAY",
                "timeIntervals.timeRange.start": start,
                "timeIntervals.timeRange.end": now,
            },
        )

    # ─── r_member_postAnalytics ───────────────────────────────────────────────
    def get_member_post_analytics(self) -> dict:
        """Analytics dos posts pessoais (últimos 30 dias)."""
        now = int(datetime.utcnow().timestamp() * 1000)
        start = now - (30 * 24 * 60 * 60 * 1000)
        return self._get(
            "/v2/memberPostAnalytics",
            params={
                "q": "member",
                "member": self.person_urn,
                "timeIntervals.timeGranularityType": "DAY",
                "timeIntervals.timeRange.start": start,
                "timeIntervals.timeRange.end": now,
            },
        )

    # ─── Dashboard combinado ──────────────────────────────────────────────────
    def get_dashboard_summary(self) -> dict:
        """Agrega dados principais para o dashboard executivo."""
        followers = self.get_follower_count()
        stats = self.get_share_statistics_last_12m()
        org = self.get_org_info()
        me = self.get_me()

        follower_count = 0
        if followers.get("ok"):
            follower_count = followers["data"].get("firstDegreeSize", 0)

        total_impressions = 0
        total_engagement = 0.0
        total_likes = 0
        total_comments = 0
        monthly_data = []

        if stats.get("ok"):
            for el in stats["data"].get("elements", []):
                s = el.get("totalShareStatistics", {})
                total_impressions += s.get("impressionCount", 0)
                total_likes += s.get("likeCount", 0)
                total_comments += s.get("commentCount", 0)
                total_engagement += s.get("engagement", 0.0)
                monthly_data.append({
                    "period_start": el.get("timeRange", {}).get("start"),
                    "impressions": s.get("impressionCount", 0),
                    "likes": s.get("likeCount", 0),
                    "comments": s.get("commentCount", 0),
                    "shares": s.get("shareCount", 0),
                    "clicks": s.get("clickCount", 0),
                    "unique_impressions": s.get("uniqueImpressionsCount", 0),
                    "engagement": round(s.get("engagement", 0.0) * 100, 2),
                })

        org_name = "VisionAi"
        org_vanity = "visionaicombr"
        if org.get("ok"):
            org_name = org["data"].get("localizedName", org_name)
            org_vanity = org["data"].get("vanityName", org_vanity)

        person_name = "Hugo Marques"
        if me.get("ok"):
            person_name = f"{me['data'].get('localizedFirstName','')} {me['data'].get('localizedLastName','')}".strip()

        return {
            "org": {
                "id": self.org_id,
                "name": org_name,
                "vanity": org_vanity,
                "url": f"https://www.linkedin.com/company/{org_vanity}",
            },
            "person": {
                "urn": self.person_urn,
                "name": person_name,
            },
            "kpis": {
                "followers": follower_count,
                "total_impressions_12m": total_impressions,
                "total_likes_12m": total_likes,
                "total_comments_12m": total_comments,
                "avg_engagement_pct": round(total_engagement / max(len(monthly_data), 1) * 100, 2),
            },
            "monthly_data": monthly_data,
        }
