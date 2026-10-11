"""
exporter.py - Générateur de notes Markdown et gestionnaire d'arborescence locale.
Organise les cours Moodle en dossiers ordonnés, convertit les textes et pages
en Markdown avec LaTeX, télécharge les fichiers et documents, et préserve
les notes personnelles de l'étudiant.
"""

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from md_converter import html_to_markdown, preserve_user_notes, sanitize_filename
from moodle_client import MoodleClient


class CourseExporter:
    def __init__(
        self,
        client: MoodleClient,
        output_dir: str = "EPITA_Moodle_Notes",
        download_files: bool = True,
        download_videos: bool = False,
        state_file: str = "state.json",
    ):
        self.client = client
        self.output_dir = output_dir
        self.download_files = download_files
        self.download_videos = download_videos
        self.state_file = state_file
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_state(self) -> None:
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ Erreur sauvegarde state.json : {e}")

    def export_course(self, course_data: Dict[str, Any]) -> Dict[str, int]:
        """Exporte un cours complet dans un dossier structuré avec Markdown et fichiers."""
        c_name = course_data.get("fullname", f"Cours_{course_data.get('id', 0)}")
        safe_c_name = sanitize_filename(c_name)
        course_dir = os.path.join(self.output_dir, safe_c_name)
        os.makedirs(course_dir, exist_ok=True)

        stats = {
            "sections": 0,
            "files": 0,
            "pages": 0,
            "qcms": 0,
            "videos": 0,
            "folders": 0,
        }

        sections_toc = []

        for sec in course_data.get("sections", []):
            s_num = sec.get("section_number", 0)
            sec_name = sec.get("name", "").strip() or f"Section {s_num}"
            safe_sec_name = f"{s_num:02d}_{sanitize_filename(sec_name)}"
            sec_dir = os.path.join(course_dir, safe_sec_name)
            os.makedirs(sec_dir, exist_ok=True)
            stats["sections"] += 1

            files_dir = os.path.join(sec_dir, "fichiers")
            pages_dir = os.path.join(sec_dir, "pages")
            qcms_dir = os.path.join(sec_dir, "qcms")

            # Catégorisation des modules pour la section
            categorized = {
                "pages": [],
                "videos": [],
                "qcms": [],
                "resources": [],
                "folders": [],
                "assigns": [],
                "labels": [],
            }

            p_idx = 1
            q_idx = 1
            f_idx = 1

            for mod in sec.get("modules", []):
                m_type = mod.get("type", "")
                m_name = mod.get("name", "").strip()
                m_desc_html = mod.get("description", "")
                m_desc_md = html_to_markdown(m_desc_html, self.client.base_url) if m_desc_html else ""
                extra = mod.get("extra", {})

                # 1. Pages de cours
                if m_type == "page":
                    os.makedirs(pages_dir, exist_ok=True)
                    safe_p_name = f"{p_idx:02d}_{sanitize_filename(m_name)}.md"
                    page_path = os.path.join(pages_dir, safe_p_name)
                    rel_page_path = f"./pages/{safe_p_name}"

                    p_content_data = extra.get("page_content", {})
                    p_html = p_content_data.get("content_html", "")
                    p_md = html_to_markdown(p_html, self.client.base_url)

                    page_full_text = f"# {m_name}\n\n"
                    page_full_text += f"> **Lien Moodle :** [{mod.get('url')}]({mod.get('url')})\n\n"
                    if m_desc_md:
                        page_full_text += f"## Description\n{m_desc_md}\n\n"
                    page_full_text += f"## Contenu du cours\n\n{p_md}\n"

                    self._write_file_safe(page_path, page_full_text)
                    stats["pages"] += 1
                    categorized["pages"].append(
                        {
                            "name": m_name,
                            "path": rel_page_path,
                            "desc": m_desc_md,
                        }
                    )
                    p_idx += 1

                # 2. Vidéos & URLs
                elif m_type == "url":
                    target_url = extra.get("target_url") or mod.get("url")
                    stats["videos"] += 1
                    categorized["videos"].append(
                        {
                            "name": m_name,
                            "url": target_url,
                            "desc": m_desc_md,
                        }
                    )

                # 3. Contenus interactifs H5P
                elif m_type == "h5pactivity":
                    stats["videos"] += 1
                    categorized["videos"].append(
                        {
                            "name": f"{m_name} (H5P Interactif)",
                            "url": mod.get("url"),
                            "desc": m_desc_md,
                        }
                    )

                # 4. Tests et QCM
                elif m_type == "quiz":
                    os.makedirs(qcms_dir, exist_ok=True)
                    safe_q_name = f"{q_idx:02d}_{sanitize_filename(m_name)}.md"
                    qcm_path = os.path.join(qcms_dir, safe_q_name)
                    rel_qcm_path = f"./qcms/{safe_q_name}"

                    q_details = extra.get("quiz_details", {})
                    q_intro_html = q_details.get("intro_html", "")
                    q_intro_md = html_to_markdown(q_intro_html, self.client.base_url)
                    rules = q_details.get("rules", [])
                    questions = q_details.get("questions", [])

                    q_full_text = f"# {m_name}\n\n"
                    q_full_text += f"- **Type :** Test / QCM Moodle\n"
                    q_full_text += f"- **Lien Moodle :** [{mod.get('url')}]({mod.get('url')})\n"
                    if rules:
                        q_full_text += f"- **Règles & Paramètres :**\n"
                        for r in rules:
                            q_full_text += f"  - {r}\n"
                    q_full_text += "\n---\n\n"

                    if q_intro_md:
                        q_full_text += f"## 📋 Consignes & Présentation\n{q_intro_md}\n\n---\n\n"

                    if questions:
                        q_full_text += "## 📝 Questions & Corrigé de la tentative\n\n"
                        for q in questions:
                            q_num = q.get("number", "Question")
                            q_grade = q.get("grade", "")
                            q_txt_md = html_to_markdown(q.get("question_html", ""), self.client.base_url)
                            q_full_text += f"### {q_num} {f'({q_grade})' if q_grade else ''}\n"
                            q_full_text += f"{q_txt_md}\n\n"

                            answers = q.get("answers", [])
                            if answers:
                                q_full_text += "**Options / Réponses :**\n"
                                for ans in answers:
                                    box = "[x]" if ans.get("checked") else "[ ]"
                                    q_full_text += f"- {box} {ans.get('text')}\n"
                                q_full_text += "\n"

                            fb_html = q.get("feedback_html", "")
                            if fb_html:
                                fb_md = html_to_markdown(fb_html, self.client.base_url)
                                q_full_text += f"> **Correction / Feedback :**\n> {fb_md}\n\n"

                    q_full_text += "## ✍️ Mes Notes / Erreurs à retenir\n<!-- Notez vos réflexions ou erreurs ici -->\n"

                    # Préserver les notes existantes sur ce QCM
                    if os.path.exists(qcm_path):
                        with open(qcm_path, "r", encoding="utf-8") as f_prev:
                            existing_q = f_prev.read()
                        q_full_text = preserve_user_notes(existing_q, q_full_text, marker="## ✍️ Mes Notes / Erreurs à retenir")

                    self._write_file_safe(qcm_path, q_full_text)
                    stats["qcms"] += 1
                    categorized["qcms"].append(
                        {
                            "name": m_name,
                            "path": rel_qcm_path,
                            "desc": m_desc_md,
                            "has_questions": len(questions) > 0,
                        }
                    )
                    q_idx += 1

                # 5. Fichiers et Ressources
                elif m_type == "resource":
                    file_info = None
                    # Vérifier dans contents
                    for item in mod.get("contents", []):
                        if item.get("fileurl"):
                            file_info = item
                            break

                    if file_info:
                        orig_fn = file_info.get("filename", "document.pdf")
                        safe_fn = sanitize_filename(orig_fn)
                        dest_fpath = os.path.join(files_dir, safe_fn)
                        rel_fpath = f"./fichiers/{safe_fn}"

                        if self.download_files:
                            os.makedirs(files_dir, exist_ok=True)
                            if self.client.download_file(file_info["fileurl"], dest_fpath):
                                stats["files"] += 1

                        categorized["resources"].append(
                            {
                                "name": m_name,
                                "filename": safe_fn,
                                "path": rel_fpath,
                                "desc": m_desc_md,
                            }
                        )
                        f_idx += 1

                # 6. Dossiers de fichiers (mod_folder)
                elif m_type == "folder":
                    folder_subfiles = []
                    safe_folder_name = sanitize_filename(m_name)
                    subfolder_dir = os.path.join(files_dir, safe_folder_name)

                    raw_files = mod.get("contents", []) or extra.get("folder_files", [])
                    if raw_files and self.download_files:
                        os.makedirs(subfolder_dir, exist_ok=True)

                    for subf in raw_files:
                        sub_fn = subf.get("filename", "")
                        sub_url = subf.get("fileurl", "")
                        if sub_fn and sub_url:
                            safe_sub_fn = sanitize_filename(sub_fn)
                            dest_subpath = os.path.join(subfolder_dir, safe_sub_fn)
                            rel_subpath = f"./fichiers/{safe_folder_name}/{safe_sub_fn}"

                            if self.download_files:
                                if self.client.download_file(sub_url, dest_subpath):
                                    stats["files"] += 1

                            folder_subfiles.append({"name": safe_sub_fn, "path": rel_subpath})

                    stats["folders"] += 1
                    categorized["folders"].append(
                        {
                            "name": m_name,
                            "desc": m_desc_md,
                            "files": folder_subfiles,
                        }
                    )

                # 7. Devoirs / DM (mod_assign)
                elif m_type == "assign":
                    assign_details = extra.get("assign_details", {})
                    a_intro = html_to_markdown(assign_details.get("intro_html", ""), self.client.base_url)
                    a_due = assign_details.get("due_date", "")
                    a_files = []

                    for af in assign_details.get("files", []):
                        af_name = sanitize_filename(af.get("filename", "sujet.pdf"))
                        dest_af = os.path.join(files_dir, af_name)
                        rel_af = f"./fichiers/{af_name}"
                        if self.download_files:
                            os.makedirs(files_dir, exist_ok=True)
                            if self.client.download_file(af["fileurl"], dest_af):
                                stats["files"] += 1
                        a_files.append({"name": af_name, "path": rel_af})

                    categorized["assigns"].append(
                        {
                            "name": m_name,
                            "url": mod.get("url"),
                            "desc": a_intro or m_desc_md,
                            "due_date": a_due,
                            "files": a_files,
                        }
                    )

                # 8. Étiquettes et textes insérés directement
                elif m_type == "label":
                    if m_desc_md:
                        categorized["labels"].append(m_desc_md)

            # Génération du README.md de la section
            sec_summary_html = sec.get("summary_html", "")
            sec_summary_md = html_to_markdown(sec_summary_html, self.client.base_url)

            sec_readme_path = os.path.join(sec_dir, "README.md")
            sec_md_content = self._build_section_readme(sec_name, sec_summary_md, categorized)

            # Préservation des notes utilisateur existantes
            if os.path.exists(sec_readme_path):
                with open(sec_readme_path, "r", encoding="utf-8") as f_prev:
                    existing_sec = f_prev.read()
                sec_md_content = preserve_user_notes(existing_sec, sec_md_content)

            self._write_file_safe(sec_readme_path, sec_md_content)

            sections_toc.append(
                {
                    "title": sec_name,
                    "rel_dir": safe_sec_name,
                    "readme_path": f"./{safe_sec_name}/README.md",
                    "counts": {
                        "pages": len(categorized["pages"]),
                        "qcms": len(categorized["qcms"]),
                        "videos": len(categorized["videos"]),
                        "files": len(categorized["resources"]) + sum(len(f["files"]) for f in categorized["folders"]),
                    },
                }
            )

        # Génération du README.md global du cours
        course_summary_html = course_data.get("summary", "")
        course_summary_md = html_to_markdown(course_summary_html, self.client.base_url)
        course_readme_content = self._build_course_readme(
            c_name,
            course_data.get("url", ""),
            course_summary_md,
            sections_toc,
            stats,
        )

        course_readme_path = os.path.join(course_dir, "README.md")
        self._write_file_safe(course_readme_path, course_readme_content)

        return stats

    def _build_section_readme(self, sec_name: str, sec_summary_md: str, categorized: Dict[str, Any]) -> str:
        """Génère le document Markdown complet pour une section de cours."""
        md_text = f"# {sec_name}\n\n"

        if sec_summary_md:
            md_text += "## 📖 Présentation du chapitre\n\n"
            md_text += f"{sec_summary_md}\n\n"

        if categorized["labels"]:
            for lbl in categorized["labels"]:
                md_text += f"{lbl}\n\n"

        has_content = False

        # Pages
        if categorized["pages"]:
            has_content = True
            md_text += "## 📄 Pages de cours\n"
            for p in categorized["pages"]:
                md_text += f"- 📄 [**{p['name']}**]({p['path']})\n"
                if p["desc"]:
                    md_text += f"  > {p['desc']}\n"
            md_text += "\n"

        # Vidéos
        if categorized["videos"]:
            has_content = True
            md_text += "## 🎬 Vidéos & Liens interactifs\n"
            for v in categorized["videos"]:
                md_text += f"- 🎬 [**{v['name']}**]({v['url']})\n"
                if v["desc"]:
                    md_text += f"  > {v['desc']}\n"
            md_text += "\n"

        # QCM
        if categorized["qcms"]:
            has_content = True
            md_text += "## 📝 Tests & QCM\n"
            for q in categorized["qcms"]:
                badge = "*(Corrigé inclus)*" if q["has_questions"] else "*(Consignes & lien)*"
                md_text += f"- 📝 [**{q['name']}**]({q['path']}) {badge}\n"
                if q["desc"]:
                    md_text += f"  > {q['desc']}\n"
            md_text += "\n"

        # Documents & Ressources
        if categorized["resources"]:
            has_content = True
            md_text += "## 📎 Documents & Fichiers de travail\n"
            for r in categorized["resources"]:
                md_text += f"- 📎 [**{r['name']}**]({r['path']}) *({r['filename']})*\n"
                if r["desc"]:
                    md_text += f"  > {r['desc']}\n"
            md_text += "\n"

        # Dossiers
        if categorized["folders"]:
            has_content = True
            md_text += "## 📁 Dossiers (Feuilles de TD & Séminaires)\n"
            for fold in categorized["folders"]:
                md_text += f"### 📁 {fold['name']}\n"
                if fold["desc"]:
                    md_text += f"> {fold['desc']}\n\n"
                if fold["files"]:
                    for sf in fold["files"]:
                        md_text += f"- 📄 [{sf['name']}]({sf['path']})\n"
                else:
                    md_text += "*(Dossier vide ou fichiers non détectés)*\n"
                md_text += "\n"

        # Devoirs
        if categorized["assigns"]:
            has_content = True
            md_text += "## 📬 Devoirs maisons & Travaux à rendre\n"
            for a in categorized["assigns"]:
                md_text += f"### 📬 [{a['name']}]({a['url']})\n"
                if a["due_date"]:
                    md_text += f"- **Date limite :** {a['due_date']}\n"
                if a["desc"]:
                    md_text += f"> {a['desc']}\n\n"
                if a["files"]:
                    md_text += "**Fichiers joints au sujet :**\n"
                    for af in a["files"]:
                        md_text += f"- 📎 [{af['name']}]({af['path']})\n"
                md_text += "\n"

        # Section Notes personnelles
        md_text += "---\n\n"
        md_text += "## ✍️ Mes Notes Personnelles\n"
        md_text += "<!-- Écris tes formules, résumés et remarques ici. Cette section est préservée lors des prochaines synchronisations. -->\n\n"

        return md_text

    def _build_course_readme(
        self,
        c_name: str,
        c_url: str,
        c_summary: str,
        sections_toc: List[Dict[str, Any]],
        stats: Dict[str, int],
    ) -> str:
        """Génère l'index principal du cours."""
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        md_text = f"# 📚 {c_name}\n\n"
        md_text += f"> **Dernière synchronisation :** {now_str}  \n"
        md_text += f"> **Lien Moodle :** [{c_url}]({c_url})\n\n"

        if c_summary:
            md_text += "## 📋 Présentation du cours\n\n"
            md_text += f"{c_summary}\n\n"

        md_text += "## 🗂️ Sommaire des chapitres & sections\n\n"
        for s in sections_toc:
            cnt = s["counts"]
            details = []
            if cnt["pages"]:
                details.append(f"{cnt['pages']} page(s)")
            if cnt["qcms"]:
                details.append(f"{cnt['qcms']} QCM")
            if cnt["videos"]:
                details.append(f"{cnt['videos']} vidéo(s)")
            if cnt["files"]:
                details.append(f"{cnt['files']} document(s)")
            detail_str = f" *({', '.join(details)})*" if details else ""

            md_text += f"- 📂 [**{s['title']}**]({s['readme_path']}){detail_str}\n"

        md_text += "\n---\n\n"
        md_text += "## 📊 Statistiques du cours\n\n"
        md_text += f"- **Chapitres / Sections :** {stats['sections']}\n"
        md_text += f"- **Pages de cours rédigées :** {stats['pages']}\n"
        md_text += f"- **Tests et QCM répertoriés :** {stats['qcms']}\n"
        md_text += f"- **Vidéos & Liens :** {stats['videos']}\n"
        md_text += f"- **Documents & Feuilles de TD téléchargés :** {stats['files']}\n\n"

        return md_text

    def build_global_index(self, courses_list: List[Dict[str, Any]], all_stats: Dict[str, Dict[str, int]]) -> None:
        """Génère le README.md global à la racine du dossier de notes."""
        os.makedirs(self.output_dir, exist_ok=True)
        global_path = os.path.join(self.output_dir, "README.md")
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

        md_text = "# 🎓 EPITA — Notes & Cours Moodle\n\n"
        md_text += f"> **Index centralisé des cours synchronisés hors-ligne**  \n"
        md_text += f"> **Dernière mise à jour :** {now_str}\n\n"
        md_text += "Cet environnement contient tous vos cours Moodle complets : descriptions détaillées, formules LaTeX, liens vidéos, QCM avec corrigés, fiches et feuilles de TD.\n\n"
        md_text += "## 📚 Vos Cours\n\n"

        tot_sections = 0
        tot_files = 0
        tot_pages = 0
        tot_qcms = 0
        tot_videos = 0

        for c in courses_list:
            cid = c.get("id")
            c_name = c.get("fullname", f"Cours {cid}")
            safe_c_name = sanitize_filename(c_name)
            c_rel_path = f"./{safe_c_name}/README.md"
            c_stat = all_stats.get(str(cid), {})

            sec_cnt = c_stat.get("sections", 0)
            file_cnt = c_stat.get("files", 0)
            page_cnt = c_stat.get("pages", 0)
            qcm_cnt = c_stat.get("qcms", 0)
            vid_cnt = c_stat.get("videos", 0)

            tot_sections += sec_cnt
            tot_files += file_cnt
            tot_pages += page_cnt
            tot_qcms += qcm_cnt
            tot_videos += vid_cnt

            sub_info = f"{sec_cnt} sections, {page_cnt} pages, {file_cnt} docs, {qcm_cnt} QCM"
            md_text += f"- 📖 [**{c_name}**]({c_rel_path}) — *{sub_info}*\n"

        md_text += "\n---\n\n"
        md_text += "## 📈 Vue d'ensemble globale\n\n"
        md_text += f"- **Nombre total de cours :** {len(courses_list)}\n"
        md_text += f"- **Total sections / chapitres :** {tot_sections}\n"
        md_text += f"- **Total pages de cours :** {tot_pages}\n"
        md_text += f"- **Total QCM & Tests :** {tot_qcms}\n"
        md_text += f"- **Total vidéos & liens :** {tot_videos}\n"
        md_text += f"- **Total documents téléchargés :** {tot_files}\n\n"
        md_text += "💡 *Astuce : Vous pouvez ouvrir ce dossier directement dans Obsidian, VS Code ou tout éditeur Markdown pour étudier et enrichir vos notes.*"

        self._write_file_safe(global_path, md_text)

    def _write_file_safe(self, path: str, content: str) -> None:
        """Écrit un fichier de manière sûre avec encodage UTF-8."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
