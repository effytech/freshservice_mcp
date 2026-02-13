"""Freshservice MCP — Solutions tools (consolidated).

Exposes 1 tool instead of the original 13:
  • manage_solution — categories, folders, articles CRUD
"""
from typing import Any, Dict, List, Optional

from ..http_client import api_get, api_post, api_put, handle_error


def register_solutions_tools(mcp) -> None:
    """Register solution-related tools on *mcp*."""

    @mcp.tool()
    async def manage_solution(
        action: str,
        # identifiers
        category_id: Optional[int] = None,
        folder_id: Optional[int] = None,
        article_id: Optional[int] = None,
        # create / update
        name: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        visibility: Optional[int] = None,
        default_category: Optional[bool] = None,
        workspace_id: Optional[int] = None,
        department_ids: Optional[List[int]] = None,
        article_type: Optional[int] = None,
        status: Optional[int] = None,
        tags: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        review_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Unified solution operations for categories, folders, and articles.

        Args:
            action: One of:
                Categories: 'list_categories', 'get_category', 'create_category', 'update_category'
                Folders: 'list_folders', 'get_folder', 'create_folder', 'update_folder'
                Articles: 'list_articles', 'get_article', 'create_article',
                          'update_article', 'publish_article'
            category_id: Category ID (get/update category, list folders, create folder)
            folder_id: Folder ID (get/update folder, list/create articles)
            article_id: Article ID (get/update/publish article)
            name: Name (create/update category or folder)
            title: Article title (create/update article)
            description: Description text/HTML
            visibility: Folder visibility (1=all, 2=logged-in, 3=agents, 4=depts)
            default_category: Mark as default (update_category)
            workspace_id: Workspace ID (create/update category)
            department_ids: Department IDs (create folder)
            article_type: 1=permanent, 2=workaround (create/update article)
            status: 1=draft, 2=published (create/update article)
            tags: Article tags list
            keywords: SEO keywords list
            review_date: ISO date for article review
        """
        action = action.lower().strip()

        # ── Categories ──
        if action == "list_categories":
            try:
                resp = await api_get("solutions/categories")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list solution categories")

        if action == "get_category":
            if not category_id:
                return {"error": "category_id required for get_category"}
            try:
                resp = await api_get(f"solutions/categories/{category_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get solution category")

        if action == "create_category":
            if not name:
                return {"error": "name required for create_category"}
            data: Dict[str, Any] = {"name": name}
            if description:
                data["description"] = description
            if workspace_id is not None:
                data["workspace_id"] = workspace_id
            try:
                resp = await api_post("solutions/categories", json=data)
                resp.raise_for_status()
                return {"success": True, "category": resp.json()}
            except Exception as e:
                return handle_error(e, "create solution category")

        if action == "update_category":
            if not category_id:
                return {"error": "category_id required for update_category"}
            data: Dict[str, Any] = {}
            for k, v in [("name", name), ("description", description),
                         ("workspace_id", workspace_id),
                         ("default_category", default_category)]:
                if v is not None:
                    data[k] = v
            if not data:
                return {"error": "No fields provided for update"}
            try:
                resp = await api_put(f"solutions/categories/{category_id}", json=data)
                resp.raise_for_status()
                return {"success": True, "category": resp.json()}
            except Exception as e:
                return handle_error(e, "update solution category")

        # ── Folders ──
        if action == "list_folders":
            if not category_id:
                return {"error": "category_id required for list_folders"}
            try:
                resp = await api_get("solutions/folders", params={"category_id": category_id})
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list solution folders")

        if action == "get_folder":
            if not folder_id:
                return {"error": "folder_id required for get_folder"}
            try:
                resp = await api_get(f"solutions/folders/{folder_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get solution folder")

        if action == "create_folder":
            if not name or not category_id or not department_ids:
                return {"error": "name, category_id and department_ids required for create_folder"}
            data: Dict[str, Any] = {
                "name": name,
                "category_id": category_id,
                "department_ids": department_ids,
                "visibility": visibility or 4,
            }
            if description:
                data["description"] = description
            try:
                resp = await api_post("solutions/folders", json=data)
                resp.raise_for_status()
                return {"success": True, "folder": resp.json()}
            except Exception as e:
                return handle_error(e, "create solution folder")

        if action == "update_folder":
            if not folder_id:
                return {"error": "folder_id required for update_folder"}
            data: Dict[str, Any] = {}
            for k, v in [("name", name), ("description", description),
                         ("visibility", visibility)]:
                if v is not None:
                    data[k] = v
            if not data:
                return {"error": "No fields provided for update"}
            try:
                resp = await api_put(f"solutions/folders/{folder_id}", json=data)
                resp.raise_for_status()
                return {"success": True, "folder": resp.json()}
            except Exception as e:
                return handle_error(e, "update solution folder")

        # ── Articles ──
        if action == "list_articles":
            if not folder_id:
                return {"error": "folder_id required for list_articles"}
            try:
                resp = await api_get("solutions/articles", params={"folder_id": folder_id})
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "list solution articles")

        if action == "get_article":
            if not article_id:
                return {"error": "article_id required for get_article"}
            try:
                resp = await api_get(f"solutions/articles/{article_id}")
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                return handle_error(e, "get solution article")

        if action == "create_article":
            if not title or not description or not folder_id:
                return {"error": "title, description and folder_id required for create_article"}
            data: Dict[str, Any] = {
                "title": title,
                "description": description,
                "folder_id": folder_id,
                "article_type": article_type or 1,
                "status": status or 1,
            }
            for k, v in [("tags", tags), ("keywords", keywords),
                         ("review_date", review_date)]:
                if v is not None:
                    data[k] = v
            try:
                resp = await api_post("solutions/articles", json=data)
                resp.raise_for_status()
                return {"success": True, "article": resp.json()}
            except Exception as e:
                return handle_error(e, "create solution article")

        if action == "update_article":
            if not article_id:
                return {"error": "article_id required for update_article"}
            data: Dict[str, Any] = {}
            for k, v in [("title", title), ("description", description),
                         ("folder_id", folder_id), ("article_type", article_type),
                         ("status", status), ("tags", tags), ("keywords", keywords),
                         ("review_date", review_date)]:
                if v is not None:
                    data[k] = v
            if not data:
                return {"error": "No fields provided for update"}
            try:
                resp = await api_put(f"solutions/articles/{article_id}", json=data)
                resp.raise_for_status()
                return {"success": True, "article": resp.json()}
            except Exception as e:
                return handle_error(e, "update solution article")

        if action == "publish_article":
            if not article_id:
                return {"error": "article_id required for publish_article"}
            try:
                resp = await api_put(f"solutions/articles/{article_id}", json={"status": 2})
                resp.raise_for_status()
                return {"success": True, "article": resp.json()}
            except Exception as e:
                return handle_error(e, "publish solution article")

        return {"error": f"Unknown action '{action}'. Valid: list_categories, get_category, create_category, update_category, list_folders, get_folder, create_folder, update_folder, list_articles, get_article, create_article, update_article, publish_article"}
