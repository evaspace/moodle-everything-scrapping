"""
moodle_client.py - Client universel pour Moodle (EPITA).
Prend en charge :
1. L'API WebService REST (wstoken)
2. Le Web Scraping complet par cookie de session (MoodleSession / Forge ID SSO)
3. La détection et résolution automatique des vidéos, pages, QCM et fichiers
"""

import json
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


class MoodleClient:
    def __init__(
        self,
        base_url: str = "https://moodle.epita.fr",
        token: Optional[str] = None,
        session_cookie: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session_cookie = session_cookie
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )
        if self.session_cookie:
            self.session.cookies.set("MoodleSession", self.session_cookie, domain=urllib.parse.urlparse(self.base_url).hostname)

        self.user_info: Dict[str, Any] = {}
        self.auth_mode: str = "none"  # "token", "cookie", or "none"

    def authenticate_with_credentials(self, username: str, password: str) -> bool:
        """Tente d'obtenir un token WebService via login/token.php."""
        token_url = f"{self.base_url}/login/token.php"
        params = {
            "username": username,
            "password": password,
            "service": "moodle_mobile_app",
        }
        try:
            resp = self.session.get(token_url, params=params, timeout=15)
            data = resp.json()
            if "token" in data:
                self.token = data["token"]
                self.auth_mode = "token"
                return True
            return False
        except Exception:
            return False

    def validate_auth(self) -> Tuple[bool, str]:
        """Vérifie la validité de l'authentification (Token ou Cookie)."""
        # 1. Vérification du token si présent
        if self.token:
            try:
                info = self.call_rest_api("core_webservice_get_site_info")
                if "userid" in info:
                    self.user_info = info
                    self.auth_mode = "token"
                    fullname = info.get("fullname", "Utilisateur")
                    return True, f"Token API valide ({fullname})"
                elif "errorcode" in info:
                    # Token invalide
                    pass
            except Exception:
                pass

        # 2. Vérification du cookie de session si présent
        if self.session_cookie:
            try:
                self.session.cookies.set("MoodleSession", self.session_cookie, domain=urllib.parse.urlparse(self.base_url).hostname)
                resp = self.session.get(f"{self.base_url}/my/", timeout=15, allow_redirects=True)
                if resp.status_code == 200 and "/login/index.php" not in resp.url:
                    self.auth_mode = "cookie"
                    # Extraction du nom d'utilisateur dans le HTML si possible
                    soup = BeautifulSoup(resp.text, "html.parser")
                    user_el = soup.find(class_=["usertext", "user-name", "userbutton"])
                    user_name = user_el.get_text(strip=True) if user_el else "Connecté (SSO)"
                    self.user_info = {"fullname": user_name}
                    return True, f"Session Web valide ({user_name})"
            except Exception as e:
                return False, f"Erreur de connexion : {e}"

        return False, "Aucune méthode d'authentification valide (Token ou MoodleSession manquant ou expiré)"

    def call_rest_api(self, function: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Appel d'une fonction de l'API REST Moodle."""
        if not self.token:
            raise ValueError("Token requis pour appeler l'API REST Moodle")
        url = f"{self.base_url}/webservice/rest/server.php"
        data = {
            "wstoken": self.token,
            "wsfunction": function,
            "moodlewsrestformat": "json",
        }
        if params:
            data.update(params)
        resp = self.session.post(url, data=data, timeout=30)
        return resp.json()

    def get_enrolled_courses(self) -> List[Dict[str, Any]]:
        """Récupère la liste de tous les cours où l'utilisateur est inscrit."""
        courses: List[Dict[str, Any]] = []

        # Mode API Token
        if self.auth_mode == "token" and self.token:
            try:
                user_id = self.user_info.get("userid")
                if not user_id:
                    self.user_info = self.call_rest_api("core_webservice_get_site_info")
                    user_id = self.user_info.get("userid")
                raw_courses = self.call_rest_api("core_enrol_get_users_courses", {"userid": user_id})
                if isinstance(raw_courses, list):
                    for c in raw_courses:
                        courses.append(
                            {
                                "id": c.get("id"),
                                "fullname": c.get("fullname", "").strip(),
                                "shortname": c.get("shortname", "").strip(),
                                "summary": c.get("summary", ""),
                                "url": f"{self.base_url}/course/view.php?id={c.get('id')}",
                            }
                        )
                    return courses
            except Exception as e:
                print(f"⚠️ Erreur récupération cours via API : {e}, bascule en web scraping...")

        # Mode Web Scraping (Cookie)
        try:
            resp = self.session.get(f"{self.base_url}/my/", timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            seen_ids = set()

            # Recherche des liens de cours dans le tableau de bord
            course_links = soup.find_all("a", href=re.compile(r"/course/view\.php\?id=(\d+)"))
            for link in course_links:
                href = link.get("href", "")
                m = re.search(r"/course/view\.php\?id=(\d+)", href)
                if not m:
                    continue
                cid = int(m.group(1))
                if cid in seen_ids or cid <= 1:
                    continue
                title = link.get_text(strip=True)
                # Si le texte du lien est vide ou un menu d'action, chercher dans le parent
                if not title or len(title) < 2:
                    card = link.find_parent(class_=["dashboard-card", "course-info-container", "card"])
                    if card:
                        title_el = card.find(class_=["coursename", "card-title"])
                        if title_el:
                            title = title_el.get_text(strip=True)

                if title and title != "Tableau de bord" and title != "Accueil":
                    seen_ids.add(cid)
                    courses.append(
                        {
                            "id": cid,
                            "fullname": title,
                            "shortname": title,
                            "summary": "",
                            "url": f"{self.base_url}/course/view.php?id={cid}",
                        }
                    )

            # Si la page /my/ n'affiche pas tous les cours, explorer /course/index.php
            if not courses:
                resp2 = self.session.get(f"{self.base_url}/course/index.php", timeout=15)
                soup2 = BeautifulSoup(resp2.text, "html.parser")
                for link in soup2.find_all("a", href=re.compile(r"/course/view\.php\?id=(\d+)")):
                    m = re.search(r"/course/view\.php\?id=(\d+)", link.get("href", ""))
                    if not m:
                        continue
                    cid = int(m.group(1))
                    if cid in seen_ids or cid <= 1:
                        continue
                    title = link.get_text(strip=True)
                    if title:
                        seen_ids.add(cid)
                        courses.append(
                            {
                                "id": cid,
                                "fullname": title,
                                "shortname": title,
                                "summary": "",
                                "url": f"{self.base_url}/course/view.php?id={cid}",
                            }
                        )

        except Exception as e:
            print(f"❌ Erreur lors de la récupération des cours : {e}")

        return courses

    def get_course_details(self, course_id: int) -> Dict[str, Any]:
        """
        Récupère l'intégralité d'un cours :
        - Titre et résumé
        - Sections et chapitres avec résumés HTML complets
        - Tous les modules (pages, vidéos, tests/QCM, devoirs, dossiers, fichiers)
        """
        course_data: Dict[str, Any] = {
            "id": course_id,
            "fullname": "",
            "summary": "",
            "url": f"{self.base_url}/course/view.php?id={course_id}",
            "sections": [],
        }

        # 1. Tentative par API WebService REST
        if self.auth_mode == "token" and self.token:
            try:
                contents = self.call_rest_api("core_course_get_contents", {"courseid": course_id})
                if isinstance(contents, list) and len(contents) > 0:
                    course_data["sections"] = self._format_api_sections(contents, course_id)
                    return course_data
            except Exception as e:
                print(f"⚠️ Erreur core_course_get_contents : {e}, repli sur web scraping...")

        # 2. Web Scraping de la page du cours
        return self._scrape_course_page(course_id)

    def _format_api_sections(self, contents: List[Dict[str, Any]], course_id: int) -> List[Dict[str, Any]]:
        """Formate et enrichit les sections récupérées via l'API REST."""
        formatted_sections = []
        for s_idx, sec in enumerate(contents):
            sec_name = sec.get("name", "").strip() or f"Section {s_idx}"
            sec_summary = sec.get("summary", "")
            modules = []

            for mod in sec.get("modules", []):
                mod_id = mod.get("id")
                mod_name = mod.get("name", "").strip()
                mod_type = mod.get("modname", "")
                mod_url = mod.get("url", f"{self.base_url}/mod/{mod_type}/view.php?id={mod_id}")
                mod_desc = mod.get("description", "")
                contents_list = mod.get("contents", [])

                mod_obj = {
                    "id": mod_id,
                    "name": mod_name,
                    "type": mod_type,
                    "url": mod_url,
                    "description": mod_desc,
                    "contents": contents_list,
                    "extra": {},
                }

                # Si c'est une page, récupérer le contenu complet
                if mod_type == "page":
                    page_content = self.get_page_content(mod_id, mod_url)
                    mod_obj["extra"]["page_content"] = page_content
                # Si c'est une vidéo ou URL externe
                elif mod_type == "url":
                    resolved_url = self.resolve_url_target(mod_id, mod_url, contents_list)
                    mod_obj["extra"]["target_url"] = resolved_url
                # Si c'est un QCM / test
                elif mod_type == "quiz":
                    quiz_details = self.get_quiz_details(mod_id, mod_url)
                    mod_obj["extra"]["quiz_details"] = quiz_details
                # Si c'est un devoir / DM
                elif mod_type == "assign":
                    assign_details = self.get_assignment_details(mod_id, mod_url)
                    mod_obj["extra"]["assign_details"] = assign_details

                modules.append(mod_obj)

            formatted_sections.append(
                {
                    "id": sec.get("id", s_idx),
                    "section_number": s_idx,
                    "name": sec_name,
                    "summary_html": sec_summary,
                    "modules": modules,
                }
            )
        return formatted_sections

    def _scrape_course_page(self, course_id: int) -> Dict[str, Any]:
        """Scrape la page HTML d'un cours pour extraire l'arborescence complète."""
        url = f"{self.base_url}/course/view.php?id={course_id}"
        resp = self.session.get(url, timeout=25)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Titre du cours
        title_tag = soup.find(["h1", "h2"], class_=["page-header-headings", "coursename", "h2"])
        course_title = title_tag.get_text(strip=True) if title_tag else soup.title.get_text(strip=True)
        course_title = re.sub(r"\s*\|\s*Plateforme.*", "", course_title).strip()

        # Résumé du cours (s'il existe en haut de page)
        summary_div = soup.find(class_=["course-summary", "course-description"])
        course_summary = summary_div.decode_contents() if summary_div else ""

        sections = []

        # Recherche des conteneurs de section Moodle 3 et 4
        # Moodle utilise soit li.section.main, soit div.course-section, soit section[id^="section-"]
        sec_elements = soup.find_all(
            ["li", "div", "section"],
            id=re.compile(r"^section-\d+"),
        )

        for s_idx, sec_el in enumerate(sec_elements):
            # Nom de la section
            name_el = sec_el.find(class_=["sectionname", "section-title"])
            sec_name = name_el.get_text(strip=True) if name_el else f"Section {s_idx}"

            # Résumé de la section (textes descriptifs au début du chapitre)
            sum_el = sec_el.find(class_=["summary", "section-summary"])
            sec_summary_html = sum_el.decode_contents() if sum_el else ""

            modules = []
            # Recherche des activités / ressources
            act_elements = sec_el.find_all(["li", "div"], class_=re.compile(r"activity|activity-item"))

            for act_el in act_elements:
                # Identifier le type (page, resource, folder, url, quiz, etc.)
                classes = " ".join(act_el.get("class", []))
                type_match = re.search(r"modtype_(\w+)", classes)
                mod_type = type_match.group(1) if type_match else "unknown"

                # Nom de l'activité
                inst_el = act_el.find(class_=["instancename", "activity-title", "activityname"])
                if inst_el:
                    # Retirer les tags cachés d'accessibilité dans le nom
                    for h in inst_el.find_all(class_=["accesshide", "sr-only"]):
                        h.decompose()
                    mod_name = inst_el.get_text(strip=True)
                else:
                    mod_name = act_el.get_text(strip=True)

                if not mod_name:
                    continue

                # Lien de l'activité
                link_el = act_el.find("a", href=re.compile(r"/mod/(\w+)/view\.php\?id=(\d+)"))
                mod_url = link_el.get("href") if link_el else ""
                mod_id = 0
                if link_el:
                    m = re.search(r"/mod/(\w+)/view\.php\?id=(\d+)", link_el.get("href", ""))
                    if m:
                        mod_type = m.group(1)
                        mod_id = int(m.group(2))

                # Description / texte d'accompagnement
                desc_el = act_el.find(class_=["contentafterlink", "activity-description"])
                mod_desc_html = desc_el.decode_contents() if desc_el else ""

                # Étiquettes (labels) : texte directement dans la page
                if mod_type in ["label", "unknown"]:
                    content_without_link = act_el.find(class_=["contentwithoutlink", "activity-content"])
                    if content_without_link:
                        mod_desc_html = content_without_link.decode_contents()
                        mod_name = "Note d'information"

                mod_obj = {
                    "id": mod_id,
                    "name": mod_name,
                    "type": mod_type,
                    "url": mod_url,
                    "description": mod_desc_html,
                    "contents": [],
                    "extra": {},
                }

                # Récupération approfondie selon le type
                if mod_type == "page" and mod_url:
                    mod_obj["extra"]["page_content"] = self.get_page_content(mod_id, mod_url)
                elif mod_type == "url" and mod_url:
                    mod_obj["extra"]["target_url"] = self.resolve_url_target(mod_id, mod_url)
                elif mod_type == "quiz" and mod_url:
                    mod_obj["extra"]["quiz_details"] = self.get_quiz_details(mod_id, mod_url)
                elif mod_type == "folder" and mod_url:
                    mod_obj["extra"]["folder_files"] = self.get_folder_files(mod_id, mod_url)
                elif mod_type == "assign" and mod_url:
                    mod_obj["extra"]["assign_details"] = self.get_assignment_details(mod_id, mod_url)
                elif mod_type == "resource" and mod_url:
                    # Résoudre le lien de téléchargement direct
                    res_file = self.resolve_resource_file(mod_id, mod_url)
                    if res_file:
                        mod_obj["contents"].append(res_file)

                modules.append(mod_obj)

            sections.append(
                {
                    "id": s_idx,
                    "section_number": s_idx,
                    "name": sec_name,
                    "summary_html": sec_summary_html,
                    "modules": modules,
                }
            )

        return {
            "id": course_id,
            "fullname": course_title,
            "summary": course_summary,
            "url": url,
            "sections": sections,
        }

    def get_page_content(self, page_id: int, page_url: str) -> Dict[str, str]:
        """Récupère le contenu HTML complet d'une Page de cours Moodle."""
        try:
            resp = self.session.get(page_url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Titre de la page
            title_el = soup.find(["h2", "h3"], class_=["main", "page-header-headings"])
            title = title_el.get_text(strip=True) if title_el else ""

            # Contenu principal
            box = soup.find(class_=["box generalbox", "page-content", "generalbox"])
            if not box:
                box = soup.find("section", id="region-main") or soup.find("div", role="main")

            content_html = box.decode_contents() if box else ""
            return {"title": title, "content_html": content_html}
        except Exception as e:
            return {"title": "", "content_html": f"<p>Erreur récupération page : {e}</p>"}

    def resolve_url_target(self, url_id: int, moodle_url: str, contents_list: Optional[List[Dict[str, Any]]] = None) -> str:
        """Détecte l'URL externe réelle (YouTube, Pod EPITA, Panopto, etc.)."""
        # Si déjà présente dans contents
        if contents_list:
            for item in contents_list:
                if item.get("type") == "url" and item.get("fileurl"):
                    return item["fileurl"]

        try:
            # Visiter la page mod/url/view.php avec redirections
            resp = self.session.get(moodle_url, timeout=15, allow_redirects=True)
            if resp.url != moodle_url and "/mod/url/" not in resp.url:
                return resp.url

            # Si non redirigé automatiquement, chercher le lien ou iframe dans le HTML
            soup = BeautifulSoup(resp.text, "html.parser")
            workaround = soup.find(class_=["urlworkaround", "generalbox"])
            if workaround:
                link = workaround.find("a")
                if link and link.get("href"):
                    return link.get("href")

            # Chercher un iframe vidéo (YouTube, Pod, etc.)
            iframe = soup.find("iframe")
            if iframe and iframe.get("src"):
                return iframe.get("src")

            # Chercher une balise video
            video = soup.find("video")
            if video:
                src = video.get("src") or (video.find("source") and video.find("source").get("src"))
                if src:
                    return src

            return resp.url
        except Exception:
            return moodle_url

    def get_quiz_details(self, quiz_id: int, quiz_url: str) -> Dict[str, Any]:
        """Extrait les règles, consignes et questions/corrigés (si relus) d'un QCM."""
        details = {
            "title": "",
            "intro_html": "",
            "rules": [],
            "review_url": "",
            "questions": [],
        }
        try:
            resp = self.session.get(quiz_url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Intro / consignes
            intro_el = soup.find(id="intro") or soup.find(class_=["quizinfo", "generalbox"])
            if intro_el:
                details["intro_html"] = intro_el.decode_contents()

            # Règles (temps imparti, dates, évaluation)
            for item in soup.find_all(class_=["quizinfo", "box"]):
                for p in item.find_all(["p", "div"]):
                    text = p.get_text(strip=True)
                    if text and any(k in text.lower() for k in ["tentative", "temps", "ouvert", "fermé", "note", "méthode"]):
                        details["rules"].append(text)

            # Recherche d'un lien de relecture de tentative (review.php)
            review_link = soup.find("a", href=re.compile(r"/mod/quiz/review\.php\?attempt=\d+"))
            if review_link:
                details["review_url"] = urllib.parse.urljoin(self.base_url, review_link.get("href"))
                # Scraper les questions et corrigés de la tentative
                details["questions"] = self._scrape_quiz_review(details["review_url"])

        except Exception as e:
            print(f"⚠️ Erreur récupération QCM {quiz_url} : {e}")

        return details

    def _scrape_quiz_review(self, review_url: str) -> List[Dict[str, Any]]:
        """Scrape une page de review de QCM pour extraire l'énoncé, options et correction."""
        questions = []
        try:
            resp = self.session.get(review_url, timeout=20)
            soup = BeautifulSoup(resp.text, "html.parser")

            que_blocks = soup.find_all("div", class_=re.compile(r"\bque\b"))
            for qb in que_blocks:
                q_no_el = qb.find(class_=["no", "qno"])
                q_num = q_no_el.get_text(strip=True) if q_no_el else "Question"

                q_grade_el = qb.find(class_=["grade", "points"])
                q_grade = q_grade_el.get_text(strip=True) if q_grade_el else ""

                # Énoncé
                qtext_el = qb.find(class_="qtext")
                q_text_html = qtext_el.decode_contents() if qtext_el else ""

                # Options et réponses
                answers = []
                ans_el = qb.find(class_="answer")
                if ans_el:
                    for row in ans_el.find_all(["div", "tr", "label"]):
                        ans_text = row.get_text(" ", strip=True)
                        if ans_text:
                            # Détecter si coché / correct
                            checked = "checked" in str(row)
                            answers.append({"text": ans_text, "checked": checked})

                # Corrigé / Explication
                feedback_el = qb.find(class_=["rightanswer", "feedback", "outcome"])
                feedback_html = feedback_el.decode_contents() if feedback_el else ""

                questions.append(
                    {
                        "number": q_num,
                        "grade": q_grade,
                        "question_html": q_text_html,
                        "answers": answers,
                        "feedback_html": feedback_html,
                    }
                )
        except Exception as e:
            print(f"⚠️ Erreur scraping review {review_url} : {e}")

        return questions

    def get_folder_files(self, folder_id: int, folder_url: str) -> List[Dict[str, str]]:
        """Scrape tous les fichiers présents dans un dossier Moodle (mod_folder)."""
        files = []
        try:
            resp = self.session.get(folder_url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            for a in soup.find_all("a", href=re.compile(r"/pluginfile\.php/")):
                file_url = urllib.parse.urljoin(self.base_url, a.get("href"))
                file_name = a.get_text(strip=True)
                if file_name and "." in file_name:
                    files.append({"filename": file_name, "fileurl": file_url})
        except Exception as e:
            print(f"⚠️ Erreur récupération dossier {folder_url} : {e}")
        return files

    def resolve_resource_file(self, resource_id: int, resource_url: str) -> Optional[Dict[str, str]]:
        """Résout l'URL directe d'un fichier ressource."""
        try:
            resp = self.session.get(resource_url, timeout=15, allow_redirects=True, stream=True)
            final_url = resp.url
            cd = resp.headers.get("Content-Disposition", "")

            filename = "document"
            if cd:
                m = re.search(r"filename\*=UTF-8''([^;]+)", cd, re.IGNORECASE)
                if m:
                    filename = urllib.parse.unquote(m.group(1).strip("\"'"))
                else:
                    m2 = re.search(r'filename="?([^";]+)"?', cd, re.IGNORECASE)
                    if m2:
                        filename = urllib.parse.unquote(m2.group(1).strip("\"'"))
            else:
                path = urllib.parse.urlparse(final_url).path
                filename = urllib.parse.unquote(os.path.basename(path))

            return {"filename": filename, "fileurl": final_url}
        except Exception:
            return None

    def get_assignment_details(self, assign_id: int, assign_url: str) -> Dict[str, Any]:
        """Extrait les consignes, date limite et documents d'un DM / devoir."""
        details = {
            "title": "",
            "intro_html": "",
            "due_date": "",
            "files": [],
        }
        try:
            resp = self.session.get(assign_url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")

            intro_el = soup.find(id="intro") or soup.find(class_=["box generalbox", "assign_intro"])
            if intro_el:
                details["intro_html"] = intro_el.decode_contents()

            # Date limite
            for row in soup.find_all("tr"):
                text = row.get_text(" ", strip=True)
                if "date limite" in text.lower() or "due date" in text.lower():
                    details["due_date"] = text

            # Fichiers joints au sujet
            for a in soup.find_all("a", href=re.compile(r"/pluginfile\.php/")):
                f_name = a.get_text(strip=True)
                if f_name and "." in f_name:
                    details["files"].append(
                        {
                            "filename": f_name,
                            "fileurl": urllib.parse.urljoin(self.base_url, a.get("href")),
                        }
                    )
        except Exception as e:
            print(f"⚠️ Erreur récupération devoir {assign_url} : {e}")

        return details

    def download_file(self, file_url: str, dest_path: str, force: bool = False) -> bool:
        """
        Télécharge un fichier Moodle vers dest_path de manière résiliente.
        Prend en charge le streaming et l'écriture atomique (.tmp -> dest).
        """
        if not force and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            return True

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        tmp_path = f"{dest_path}.tmp"

        download_url = file_url
        if self.auth_mode == "token" and self.token and "token=" not in download_url:
            separator = "&" if "?" in download_url else "?"
            download_url = f"{download_url}{separator}token={self.token}"

        try:
            with self.session.get(download_url, stream=True, timeout=60) as resp:
                if resp.status_code != 200:
                    return False
                with open(tmp_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
            os.replace(tmp_path, dest_path)
            return True
        except Exception as e:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            print(f"❌ Échec de téléchargement pour {os.path.basename(dest_path)} : {e}")
            return False
