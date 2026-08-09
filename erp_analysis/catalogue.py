# erp_analysis/catalogue.py
import os
import zipfile
import shutil
from typing import Optional, Dict, Any, List

import frappe
from frappe.utils import get_site_path, get_url


# Where all flip catalogues will live on the WEBSITE app
# Final folder per catalogue:
#   /home/erpnext/frappe-bench/apps/printechs_website/printechs_website/www/catalogue/<DOC.NAME>/
WEBSITE_CATALOGUE_ROOT = "/home/erpnext/frappe-bench/apps/printechs_website/printechs_website/www/catalogue"


# =======================================================
# 0) CORE UNZIP HELPERS
# =======================================================

def _unzip_catalogue(doc):
    """Core logic to unzip the flip package for a given E Catalogue doc."""
    if not doc.flip_package:
        frappe.msgprint("No Flip Package (ZIP) attached on this catalogue.")
        return

    # 1) Resolve File record for the attached ZIP
    file_doc = frappe.get_doc("File", {"file_url": doc.flip_package})
    zip_path = file_doc.get_full_path()
    zip_path = os.path.abspath(zip_path)

    if not os.path.exists(zip_path):
        frappe.throw(f"ZIP file not found on disk: {zip_path}")

    if not zip_path.lower().endswith(".zip"):
        frappe.throw(f"File is not a ZIP: {zip_path}")

    # 2) Build output directory in WEBSITE app:
    #    <WEBSITE_CATALOGUE_ROOT>/<doc.name>/
    output_dir = os.path.join(WEBSITE_CATALOGUE_ROOT, doc.name)

    # Optional: remove old content so stale JS/CSS/images are cleared
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    os.makedirs(output_dir, exist_ok=True)

    # 3) Extract ZIP safely
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(output_dir)

        frappe.msgprint(
            f"Unzipped successfully to /catalogue/{doc.name}/",
            alert=True,
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "E Catalogue Unzip Failed")
        frappe.throw("Failed to unzip flip package. Check Error Log.")


@frappe.whitelist()
def unzip_catalogue(catalogue_id: str):
    """
    Manual API/console helper to force unzip for one catalogue.
    You can call:
      erp_analysis.catalogue.unzip_catalogue?catalogue_id=CAT-2025-00001
    or from bench console.
    """
    doc = frappe.get_doc("E Catalogue", catalogue_id)
    _unzip_catalogue(doc)
    return {"message": "OK"}


def _ensure_flip_unpacked(doc):

    output_dir = os.path.join(WEBSITE_CATALOGUE_ROOT, doc.name)

    entry_file = doc.flip_entry_file or "index.html"
    index_path = os.path.join(output_dir, entry_file)

    # If index exists → do not unzip again
    if os.path.exists(index_path):
        return f"/catalogue/{doc.name}"

    # Else unzip now
    _unzip_catalogue(doc)

    return f"/catalogue/{doc.name}"


# =======================================================
# 1) CATALOGUE LIST
# =======================================================

@frappe.whitelist(methods=["GET"])
def get_OLDcatalogues_listold(
    item_group: Optional[str] = None,
    brand: Optional[str] = None,
    search: Optional[str] = None,
    enabled: Optional[int] = 1,
) -> Dict[str, Any]:
    """
    List catalogues for mobile listing screen.

    Query params:
      item_group (optional) - filter by Item Group / Category
      brand      (optional) - filter by Brand
      search     (optional) - substring search on title
      enabled    (optional) - 1/0 or None to ignore

    Response:
    {
      "message": {
        "catalogues": [
          {
            "id": "...",
            "title": "...",
            "item_group": "...",
            "brand": "...",
            "thumbnail_url": "...",
            "description": "...",
            "flip_available": true/false,
            "video_count": 0,
            "youtube_url": "..."
          }
        ],
        "total": 1
      }
    }
    """
    filters: Dict[str, Any] = {}
    if enabled is not None:
        filters["enabled"] = int(enabled)
    if item_group:
        filters["item_group"] = item_group
    if brand:
        filters["brand"] = brand

    rows = frappe.get_all(
        "E Catalogue",
        filters=filters,
        fields=[
            "name",
            "title",
            "item_group",
            "brand",
            "thumbnail_image",
            "description",
            "flip_package",
            "flip_entry_file",
            "sort_order",
            "youtube_url",
        ],
        order_by="sort_order asc, title asc",
    )

    base_url = get_url()
    result: List[Dict[str, Any]] = []

    for r in rows:
        # Basic search on title (client-style)
        if search and search.lower() not in (r.title or "").lower():
            continue

        thumb_url = f"{base_url}{r.thumbnail_image}" if r.thumbnail_image else None

        video_count = frappe.db.count(
            "E Catalogue Video",
            {
                "parent": r.name,
                "parenttype": "E Catalogue",
                "parentfield": "videos",
                "enabled": 1,
            },
        )

        flip_available = bool(r.flip_package)

        result.append(
            {
                "id": r.name,
                "title": r.title or r.name,
                "item_group": r.item_group,
                "brand": r.brand,
                "thumbnail_url": thumb_url,
                "description": r.description or "",
                "flip_available": flip_available,
                "video_count": video_count,
                "youtube_url": r.youtube_video_url or None,
            }
        )

    return {"message": {"catalogues": result, "total": len(result)}}


@frappe.whitelist(methods=["GET"])
def get_catalogues_list(
    item_group: Optional[str] = None,
    brand: Optional[str] = None,
    search: Optional[str] = None,
    enabled: Optional[int] = 1,
) -> Dict[str, Any]:
    filters: Dict[str, Any] = {}
    if enabled is not None:
        filters["enabled"] = int(enabled)
    if item_group:
        filters["item_group"] = item_group
    if brand:
        filters["brand"] = brand

    rows = frappe.get_all(
        "E Catalogue",
        filters=filters,
        fields=[
            "name",
            "title",
            "item_group",
            "brand",
            "thumbnail_image",
            "description",
            "flip_package",
            "flip_entry_file",
            "sort_order",
            "youtube_url",
        ],
        order_by="sort_order asc, title asc",
    )

    base_url = get_url()
    result: List[Dict[str, Any]] = []

    for r in rows:
        if search and search.lower() not in (r.title or "").lower():
            continue

        thumb_url = f"{base_url}{r.thumbnail_image}" if r.thumbnail_image else None

        # Count enabled videos from child table
        video_count = frappe.db.count(
            "E Catalogue Video",
            {
                "parent": r.name,
                "parenttype": "E Catalogue",
                "parentfield": "videos",
                "enabled": 1,
            },
        )

        # Fetch videos from child table ← ADD THIS SECTION
        video_rows = frappe.get_all(
            "E Catalogue Video",
            filters={
                "parent": r.name,
                "parenttype": "E Catalogue",
                "parentfield": "videos",
                "enabled": 1,
            },
            fields=[
                "title",
                "video_type",
                "youtube_url",
                "local_video",
                "enabled",
            ],
            order_by="idx asc",  # Maintain order
        )

        # Transform video rows to response format ← ADD THIS SECTION
        videos_list = []
        for video_row in video_rows:
            video_data = {
                "title": video_row.title or "",
                "video_type": video_row.video_type or "YouTube",
                "enabled": bool(video_row.enabled),
            }
            
            if video_row.video_type == "YouTube":
                video_data["youtube_url"] = video_row.youtube_url or None
                video_data["local_video_url"] = None
            elif video_row.video_type == "Local":
                local_video_url = f"{base_url}{video_row.local_video}" if video_row.local_video else None
                video_data["local_video_url"] = local_video_url
                video_data["youtube_url"] = None
            else:
                video_data["youtube_url"] = video_row.youtube_url or None
                video_data["local_video_url"] = None
            
            videos_list.append(video_data)

        flip_available = bool(r.flip_package)

        result.append(
            {
                "id": r.name,
                "title": r.title or r.name,
                "item_group": r.item_group,
                "brand": r.brand,
                "thumbnail_url": thumb_url,
                "description": r.description or "",
                "flip_available": flip_available,
                "video_count": video_count,
                "youtube_video_url": r.youtube_video_url or None,
                "videos": videos_list,  # ← ADD THIS LINE
            }
        )

    return {"message": {"catalogues": result, "total": len(result)}}

# =======================================================
# 2) CATALOGUE DETAIL (FLIP URL + VIDEOS)
# =======================================================

@frappe.whitelist(methods=["GET"])
def get_catalogue_detail(
    catalogue_id: str,
    customer: Optional[str] = None,
    project: Optional[str] = None,
    include_videos: int = 1,
) -> Dict[str, Any]:
    """
    Full catalogue details for a details screen.

    Query params:
      catalogue_id (required)
      customer, project (optional) - filter videos
      include_videos (1/0)

    Response:
    {
      "message": {
        "catalogue_id": "...",
        "title": "...",
        "item_group": "...",
        "brand": "...",
        "description": "...",
        "thumbnail_url": "...",
        "flip_url": "https://.../catalogue/<id>/index.html" | null,
        "videos": [...]
      }
    }
    """
    doc = frappe.get_doc("E Catalogue", catalogue_id)
    base_url = get_url()

    detail: Dict[str, Any] = {
        "catalogue_id": doc.name,
        "title": doc.title,
        "item_group": getattr(doc, "item_group", None),
        "brand": getattr(doc, "brand", None),
        "description": doc.description or "",
        "enabled": bool(getattr(doc, "enabled", 1)),
        "thumbnail_url": f"{base_url}{doc.thumbnail_image}"
        if getattr(doc, "thumbnail_image", None)
        else None,
    }

    # Flipbook URL (wrapped in try so bad ZIP won't break everything)
    try:
        if doc.flip_package:
            web_folder = _ensure_flip_unpacked(doc)
            entry_file = (doc.flip_entry_file or "index.html").lstrip("/")
            detail["flip_url"] = f"{base_url}{web_folder}/{entry_file}"
        else:
            detail["flip_url"] = None
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            title=f"E Catalogue flip unpack failed: {doc.name}",
        )
        detail["flip_url"] = None

    if int(include_videos or 0):
        detail["videos"] = _get_videos_for_catalogue(doc, customer, project)
    else:
        detail["videos"] = []

    return {"message": detail}


# =======================================================
# 3) SIMPLE API: ONLY FLIP URL
# =======================================================


@frappe.whitelist(methods=["GET"], allow_guest=True)
def get_catalogue_flip_url(catalogue_id: str) -> Dict[str, Any]:
    """Get the flip URL for a catalogue. Returns JSON error if catalogue not found."""
    try:
        # Ensure JSON response - wrap in try to handle cases where frappe.local might not be initialized
        try:
            frappe.local.response["type"] = "json"
        except (AttributeError, KeyError):
            pass
        
        # Clear any existing messages first
        try:
            frappe.clear_messages()
        except Exception:
            pass
        
        # Validate input
        if not catalogue_id:
            return {
                "error": "catalogue_id parameter is required",
                "catalogue_id": None,
            }
        
        # Check if catalogue exists first to avoid DoesNotExistError
        if not frappe.db.exists("E Catalogue", catalogue_id):
            return {
                "error": f"E Catalogue '{catalogue_id}' not found",
                "catalogue_id": catalogue_id,
            }
        
        try:
            doc = frappe.get_doc("E Catalogue", catalogue_id)
        except frappe.DoesNotExistError:
            return {
                "error": f"E Catalogue '{catalogue_id}' not found",
                "catalogue_id": catalogue_id,
            }
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "get_catalogue_flip_url error")
            return {
                "error": f"Error fetching catalogue: {str(e)}",
                "catalogue_id": catalogue_id,
            }

        base_url = get_url()

        try:
            web_folder = _ensure_flip_unpacked(doc)  # "/catalogue/<doc.name>"
            entry_file = (doc.flip_entry_file or "index.html").lstrip("/")
            flip_url = f"{base_url}{web_folder}/{entry_file}"
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "get_catalogue_flip_url unpack error")
            return {
                "error": f"Error preparing catalogue flip URL: {str(e)}",
                "catalogue_id": doc.name,
                "title": getattr(doc, "title", ""),
            }

        # Clear any messages from unzip operations before returning
        try:
            frappe.clear_messages()
        except Exception:
            pass

        # Frappe API handler automatically wraps in "message", so return data directly
        return {
            "catalogue_id": doc.name,
            "title": doc.title,
            "flip_url": flip_url,
        }
    except Exception as e:
        # Catch-all for any unexpected errors
        frappe.log_error(frappe.get_traceback(), "get_catalogue_flip_url unexpected error")
        return {
            "error": f"Unexpected error: {str(e)}",
            "catalogue_id": catalogue_id if 'catalogue_id' in locals() else None,
        }

# =======================================================
# 4) INTERNAL: VIDEO LIST
# =======================================================

def _get_videos_for_catalogue(
    doc,
    customer: Optional[str] = None,
    project: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Returns list of enabled videos from child table E Catalogue Video.
    Filters by customer/project if provided.
    """

    filters: Dict[str, Any] = {
        "parent": doc.name,
        "parenttype": "E Catalogue",
        "parentfield": "videos",
        "enabled": 1,
    }

    if customer:
        filters["customer"] = customer
    if project:
        filters["project"] = project

    rows = frappe.get_all(
        "E Catalogue Video",
        filters=filters,
        fields=[
            "name",
            "title",
            "video_type",
            "youtube_url",
            "local_video",
            "thumbnail_image",
            "customer",
            "project",
            "description",
            "sort_order",
        ],
        order_by="sort_order asc, creation asc",
    )

    base_url = get_url()
    videos: List[Dict[str, Any]] = []

    for v in rows:
        if v.video_type == "Local" and v.local_video:
            video_url = f"{base_url}{v.local_video}"
        else:
            video_url = v.youtube_url

        thumb_url = f"{base_url}{v.thumbnail_image}" if v.thumbnail_image else None

        videos.append(
            {
                "id": v.name,
                "title": v.title or "",
                "video_type": v.video_type,
                "video_url": video_url,
                "thumbnail_url": thumb_url,
                "customer": v.customer,
                "project": v.project,
                "description": v.description or "",
            }
        )

    return videos


@frappe.whitelist(methods=["GET"])
def get_catalogue_pages(catalogue_id: str, **kwargs):
	"""Mobile contract alias for catalogue detail/pages."""
	return get_catalogue_detail(catalogue_id=catalogue_id, **kwargs)