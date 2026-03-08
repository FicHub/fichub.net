from typing import TYPE_CHECKING, Any, cast
import contextlib
from enum import IntEnum
import json
import math
from pathlib import Path
import random
import shutil
import time

from flask import (
    Flask,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
import markupsafe
from werkzeug.exceptions import NotFound

if TYPE_CHECKING:
    from flask.typing import ResponseReturnValue

from fichub_net import ax, ebook, es, util
from fichub_net.db import FicBlacklist, FicInfo, RequestLog, RequestSource
from fichub_net.ip_tag import TAGGED_IP_RANGES, ip_is_datacenter, load_ip_ranges
from fichub_net.limiter import Limiter
from fichub_net.rl_conf import (
    DYNAMIC_RATE_LIMIT,
    IP_TAG_SOURCES,
    LIMIT_UPSTREAMS,
    LIMIT_UPSTREAMS_EXTRA,
    NO_LIMIT_UPSTREAMS,
    WEIRD_UPSTREAMS,
)

app = Flask(__name__, static_url_path="", static_folder="../../static/")

NODE_NAME = "orion"
CACHE_BUSTER = "26"
CSS_CACHE_BUSTER = CACHE_BUSTER
JS_CACHE_BUSTER = CACHE_BUSTER
CURRENT_CSS = ""  # note: empty string is treated as None

# may treat requests from these sources as being proxied for a user
# gil: 142.132.180.201
TRUSTED_UPSTREAMS = {
    "142.132.180.201",
}


class MissingExportError(Exception):
    pass


class WebError(IntEnum):
    success = 0
    no_query = -1
    invalid_etype = -2
    export_failed = -3
    ensure_failed = -4
    lookup_failed = -5
    ax_dead = -6
    greylisted = -7
    internal = -8
    internal_datacenter = -9
    internal_strange = -10


error_messages = {
    WebError.success: "success",
    WebError.no_query: "no query",
    WebError.invalid_etype: "invalid etype",
    WebError.export_failed: "export failed",
    WebError.ensure_failed: "ensure failed",
    WebError.lookup_failed: "lookup failed",
    WebError.ax_dead: "backend api is down",
    WebError.greylisted: "exports are unavailable for this fic, possibly due to author request",
    WebError.internal: "internal error",
    WebError.internal_datacenter: "internal error",
    WebError.internal_strange: "internal error",
}


def get_err(err: WebError, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    base = {"err": int(err), "msg": error_messages[err]}
    if extra is not None:
        base.update(extra)
    return base


@app.errorhandler(404)
def page_not_found(_e: Exception) -> ResponseReturnValue:
    return render_template("404.html"), 404


@app.route("/api/")
def api_landing_trailing_slash() -> ResponseReturnValue:
    return redirect(url_for("api_landing"))


@app.route("/api")
def api_landing() -> ResponseReturnValue:
    return render_template("api.html")


@app.route("/")
def index() -> ResponseReturnValue:
    url_id = request.args.get("id", "").strip()
    return index_impl(url_id, False)


def index_impl(url_id: str, legacy: bool) -> ResponseReturnValue:
    from_pw = request.args.get("from_pw", "").strip()

    blacklisted = False
    greylisted = False
    links = []
    fic_info = None
    with contextlib.suppress(Exception):
        if legacy and len(url_id) > 1:
            fis = FicInfo.select(url_id)
            if len(fis) == 1:
                blacklisted = FicBlacklist.blacklisted(url_id)
                greylisted = FicBlacklist.greylisted(url_id)
                fic_info = fis[0]

                epub_rl = RequestLog.most_recent_by_url_id("epub", url_id)
                if epub_rl is None:
                    # we always generate the epub first, so if we don't have it something went
                    # horribly wrong
                    msg = "uh oh"
                    raise MissingExportError(msg)

                slug = ebook.build_file_slug(fic_info.title, fic_info.author, url_id)
                eh = epub_rl.export_file_hash
                if eh is None:
                    eh = "unknown"
                epub_url = url_for(
                    "get_cached_export",
                    etype="epub",
                    url_id=url_id,
                    fname=f"{slug}.epub",
                    h=eh,
                )

                links = [("epub", True, epub_url)]
                for etype in ebook.EXPORT_TYPES:
                    if etype == "epub":
                        continue
                    pe = ebook.find_existing_export(etype, url_id, eh)
                    if pe is None:
                        # for any etype that hasn't already been exported or is out of date,
                        # create a (re)generate link
                        link = url_for(
                            "get_cached_export_partial",
                            etype=etype,
                            url_id=url_id,
                            cv=CACHE_BUSTER,
                            eh=eh,
                        )
                        links.append((etype, False, link))
                    else:
                        # otherwise build the direct link
                        fname = slug + ebook.EXPORT_SUFFIXES[etype]
                        fhash = pe[1]
                        link = url_for(
                            "get_cached_export",
                            etype=etype,
                            url_id=url_id,
                            fname=fname,
                            h=fhash,
                        )
                        links.append((etype, True, link))

    if greylisted:
        links = []

    resp = make_response(
        render_template(
            "index.html",
            from_pw=from_pw,
            fic_info=fic_info,
            blacklisted=blacklisted,
            greylisted=greylisted,
            links=links,
        )
    )
    if legacy:
        resp.headers["X-Robots-Tag"] = "noindex"
    return resp


@app.route("/changes")
def changes() -> ResponseReturnValue:
    return redirect(url_for("index"))


@app.route("/fic/<url_id>")
def fic_info(url_id: str) -> ResponseReturnValue:
    all_info = FicInfo.select(url_id)
    if len(all_info) < 1:
        # entirely unknown fic, 404
        return page_not_found(NotFound())
    fic_info = all_info[0]

    return redirect(url_for("index", q=fic_info.source, id=fic_info.id))


@app.route("/cache/", defaults={"_page": 1})
@app.route("/cache/<int:_page>")
def cache_listing_deprecated(_page: int) -> ResponseReturnValue:
    return redirect(url_for("index"))


@app.route("/cache/today/", defaults={"_page": 1})
@app.route("/cache/today/<int:_page>")
def cache_listing_today(_page: int) -> ResponseReturnValue:
    return redirect(url_for("index"))


@app.route("/cache/<int:_year>/<int:_month>/<int:_day>/", defaults={"_page": 1})
@app.route("/cache/<int:_year>/<int:_month>/<int:_day>/<int:_page>")
def cache_listing(
    _year: int, _month: int, _day: int, _page: int
) -> ResponseReturnValue:
    return redirect(url_for("index"))


@app.route("/popular/", defaults={"_page": 1})
@app.route("/popular/<int:_page>")
def popular_listing(_page: int) -> ResponseReturnValue:
    return render_template("popular_outmoded.html")


@app.route("/search/author/<_q>")
def search_author(_q: str) -> ResponseReturnValue:
    return redirect(url_for("index"))


def try_ensure_export(etype: str, url_id: str) -> str | None:
    key = f"{etype}_fname"
    res = ensure_export(etype, url_id, url_id)
    if "err" in res or key not in res:
        return None
    if res[key] is None or isinstance(res[key], Path):
        return cast("str | None", str(res[key]))
    if res[key] is None or isinstance(res[key], str):
        return cast("str | None", str(res[key]))
    return None


def get_request_source() -> RequestSource:
    automated = request.args.get("automated", None) == "true"
    remote_addr = request.remote_addr
    if remote_addr is not None and remote_addr in TRUSTED_UPSTREAMS:
        remote_addr = request.headers.get("X-Forwarded-For", remote_addr)
    if remote_addr is None:
        remote_addr = "unknown"
    return RequestSource.upsert(automated, request.url_root, remote_addr)


def create_export(
    etype: str, meta: FicInfo, chapters: dict[int, ax.Chapter]
) -> tuple[Path, str]:
    # returns fname, fhash
    if etype == "epub":
        return ebook.create_epub(meta, chapters)
    if etype == "html":
        return ebook.create_html_bundle(meta, chapters)
    if etype in ["mobi", "pdf"]:
        return ebook.convert_epub(meta, chapters, etype)

    msg = f"err: unknown etype: {etype}"
    raise ebook.InvalidETypeError(msg)


def ensure_export(etype: str, query: str, url_id: str | None = None) -> dict[str, Any]:
    app.logger.info(f"ensure_export: query: {query}")
    if etype not in ebook.EXPORT_TYPES:
        return get_err(WebError.invalid_etype, {"fn": "ensure_export", "etype": etype})

    source = get_request_source()

    authorization = request.headers.get("Authorization", None)
    if authorization is None:
        if (
            source.description not in LIMIT_UPSTREAMS
            and source.description not in NO_LIMIT_UPSTREAMS
        ):
            LIMIT_UPSTREAMS[source.description] = 0.1
        if source.description in LIMIT_UPSTREAMS:
            v = LIMIT_UPSTREAMS[source.description]
            o = LIMIT_UPSTREAMS_EXTRA.get(source.description, 0.0)
            limit_d = 1 + (random.random() * v) + o
            app.logger.info(
                f"  limiting {source.description}: v={v:0.3} o={o:0.3} d={limit_d:0.3} ts={time.time()}"
            )
            time.sleep(limit_d)

    notes = []
    ax_alive = ax.alive()
    if not ax_alive:
        app.logger.info("ensure_export: ax is not alive :(")
        if url_id is None or len(FicInfo.select(url_id)) != 1:
            return get_err(WebError.ax_dead)
        # otherwise fallthrough
        notes += ["backend api is down; results may be stale"]

    init_time_ms = int(time.time() * 1000)
    meta = None
    lres = None
    try:
        if not ax_alive:
            meta = FicInfo.select(url_id)[0]
        else:
            lres = ax.lookup(query)
            if "err" in lres:
                end_time_ms = int(time.time() * 1000)
                RequestLog.insert(
                    source,
                    etype,
                    query,
                    end_time_ms - init_time_ms,
                    None,
                    json.dumps(lres),
                    None,
                    None,
                    None,
                    None,
                )
                lres["upstream"] = True
                return lres
            meta = FicInfo.parse(lres)
    except Exception:
        app.logger.exception("ensure_export: ^ something went wrong doing ax.lookup :/")

        return get_err(WebError.lookup_failed)

    meta_dict = meta.to_json()

    info_time_ms = int(time.time() * 1000)
    info_request_ms = info_time_ms - init_time_ms

    # attempt to find previous epub export if it exists...
    try:
        existing_epub = None
        if meta.content_hash is not None:
            existing_epub = ebook.find_existing_export(
                "epub", meta.id, meta.content_hash
            )

        existing_export = None
        if etype == "epub":
            existing_export = existing_epub
        elif existing_epub is not None:
            _epub_fname, ehash = existing_epub
            existing_export = ebook.find_existing_export(etype, meta.id, ehash)

        if existing_export is not None:
            app.logger.info(
                f"ensure_export({etype}, {query}): attempting to reuse previous export for {meta.id}"
            )
            fname, fhash = existing_export
            meta_string = ebook.metadata_string(meta)

            slug = ebook.build_file_slug(meta.title, meta.author, meta.id)
            suff = ebook.EXPORT_SUFFIXES[etype]
            export_url = url_for(
                "get_cached_export",
                etype=etype,
                url_id=meta.id,
                fname=f"{slug}{suff}",
                h=fhash,
            )

            end_time_ms = int(time.time() * 1000)
            export_ms = end_time_ms - info_time_ms

            RequestLog.insert(
                source,
                etype,
                query,
                info_request_ms,
                meta.id,
                json.dumps(lres),
                export_ms,
                str(fname),
                fhash,
                export_url,
            )

            app.logger.info(
                f"ensure_export({etype}, {query}): reusing previous export for {meta.id}"
            )
            return {
                "urlId": meta.id,
                "info": meta_string,
                f"{etype}_fname": fname,
                "hash": fhash,
                "url": export_url,
                "meta": meta_dict,
                "slug": slug,
                "hashes": {etype: fhash},
                "notes": notes,
            }
    except Exception:
        app.logger.exception(
            "ensure_export: ^ something went wrong trying to reuse existing export :/"
        )

    etext = None
    try:
        # TODO: we could be timing this too...
        meta_string = ebook.metadata_string(meta)
        chapters = ax.fetch_chapters(meta)

        # actually do the export
        fname, fhash = create_export(etype, meta, chapters)

        slug = ebook.build_file_slug(meta.title, meta.author, meta.id)
        suff = ebook.EXPORT_SUFFIXES[etype]
        export_url = url_for(
            "get_cached_export",
            etype=etype,
            url_id=meta.id,
            fname=f"{slug}{suff}",
            h=fhash,
        )

        end_time_ms = int(time.time() * 1000)
        export_ms = end_time_ms - info_time_ms

        RequestLog.insert(
            source,
            etype,
            query,
            info_request_ms,
            meta.id,
            json.dumps(lres),
            export_ms,
            str(fname),
            fhash,
            export_url,
        )

        return {
            "urlId": meta.id,
            "info": meta_string,
            f"{etype}_fname": fname,
            "hash": fhash,
            "url": export_url,
            "meta": meta_dict,
            "slug": slug,
            "hashes": {etype: fhash},
        }
    except Exception as e:
        end_time_ms = int(time.time() * 1000)
        export_ms = end_time_ms - info_time_ms
        RequestLog.insert(
            source,
            etype,
            query,
            end_time_ms - init_time_ms,
            meta.id,
            json.dumps(lres),
            export_ms,
            None,
            None,
            None,
        )

        if (
            e.args is not None
            and len(e.args) > 0
            and isinstance(e, ax.MissingChapterError | ebook.InvalidETypeError)
        ):
            etext = e.args[0]

        app.logger.exception("ensure_export: ^ something went wrong :/")

    return get_err(
        WebError.export_failed,
        {
            "msg": f"{etype} export failed\nplease try again in a few minutes, or report this on discord if the issue persists",
            "etext": etext,
            "meta": meta_dict,
        },
    )


def legacy_cache_redirect(etype: str, fname: str) -> ResponseReturnValue:
    fhash = request.args.get("h", None)
    url_id = fname
    if url_id.find("-") >= 0:
        url_id = url_id.split("-")[-1]
    suff = ebook.EXPORT_SUFFIXES[etype]
    url_id = url_id.removesuffix(suff)
    if fhash is None:
        return redirect(
            url_for(
                "get_cached_export_partial", etype=etype, url_id=url_id, cv=CACHE_BUSTER
            )
        )
    return redirect(
        url_for(
            "get_cached_export",
            etype=etype,
            url_id=url_id,
            fname=f"{fhash}{suff}",
            cv=CACHE_BUSTER,
        )
    )


@app.route("/epub/<fname>")
def get_cached_epub_v0(fname: str) -> ResponseReturnValue:
    return legacy_cache_redirect("epub", fname)


@app.route("/html/<fname>")
def get_cached_html_v0(fname: str) -> ResponseReturnValue:
    return legacy_cache_redirect("html", fname)


@app.route("/cache/<etype>/<url_id>/<fname>")
def get_cached_export(etype: str, url_id: str, fname: str) -> ResponseReturnValue:
    if etype not in ebook.EXPORT_TYPES:
        # if this is an unsupported export type, 404
        return page_not_found(NotFound())

    mimetype = ebook.EXPORT_MIMETYPES[etype]
    suff = ebook.EXPORT_SUFFIXES[etype]
    if not fname.endswith(suff):
        # we have a request for the wrong extension, 404
        return page_not_found(NotFound())

    _source_limiter, limit_resp = maybe_limit_request()
    if limit_resp is not None:
        return limit_resp

    if FicBlacklist.check(url_id):
        # blacklisted fic, 404
        return render_template("fic_info_blacklist.html"), 404

    fhash = request.args.get("h", None)
    fdir, sfdir = ebook.build_export_path(etype, url_id)
    if fhash is not None:
        # if the request is for a specific slug, try to serve it directly
        rname = fname
        fname = f"{fhash}{suff}"
        if not (fdir / fname).is_file() and (sfdir / fname).is_file():
            fdir.mkdir(parents=True)
            shutil.move((sfdir / fname), (fdir / fname))
        if (fdir / fname).is_file():
            return send_from_directory(
                fdir,
                fname,
                as_attachment=True,
                download_name=rname,
                mimetype=mimetype,
                max_age=(60 * 60 * 24 * 365),
            )
        # fall through...

    # otherwise find the most recent export and give them that
    all_info = FicInfo.select(url_id)
    if len(all_info) < 1:
        # entirely unknown fic, 404
        return page_not_found(NotFound())
    fic_info = all_info[0]
    slug = ebook.build_file_slug(fic_info.title, fic_info.author, url_id)
    rl = RequestLog.most_recent_by_url_id(etype, url_id)
    if rl is None:
        return page_not_found(NotFound())

    if not (fdir / f"{rl.export_file_hash}{suff}").is_file():
        # the most recent export is missing for some reason... regenerate it
        return get_cached_export_partial(etype, url_id)

    # redirect back to ourself with the correct filename
    return redirect(
        url_for(
            "get_cached_export",
            etype=etype,
            url_id=url_id,
            fname=f"{slug}{suff}",
            h=rl.export_file_hash,
        )
    )


@app.route("/cache/<etype>/<url_id>")
def get_cached_export_partial(etype: str, url_id: str) -> ResponseReturnValue:
    if etype not in ebook.EXPORT_TYPES:
        # if this is an unsupported export type, 404
        return page_not_found(NotFound())

    # otherwise we have a url_id we need to export
    fname = try_ensure_export(etype, url_id)
    if fname is None:
        # if we failed to generate the export, 503
        return render_template("503_janus.html"), 503

    return get_cached_export(etype, url_id, fname)


def get_fixits(q: str) -> list[str]:
    fixits: list[str] = []
    if q.find("tvtropes.org") >= 0:
        fixits += [
            "(note that tvtropes.org is not directly supported; instead, use the url of the actual fic)"
        ]
    if q.find("http://") != 0 and q.find("https://") != 0:
        fixits += ["(please try a full url including http:// or https:// at the start)"]
    if q.find("fanfiction.net") >= 0:
        fixits += [
            "fanfiction.net is fragile at the moment; please try again later or check the discord"
        ]
    if q.find("fanfiction.net/u/") >= 0:
        fixits += [
            "user pages on fanfiction.net are not currently supported -- please try a specific story"
        ]
    if q.find("fictionpress.com") >= 0:
        fixits += [
            "fictionpress.com is fragile at the moment; please try again later or check the discord"
        ]

    with contextlib.suppress(Exception):
        fis = es.search(q, limit=15)
        for fi in fis:
            fixits += [
                f"<br/>did you mean <a href=/fic/{fi.id}>{fi.title} by {fi.author}</a>?"
            ]

    return fixits


def get_limiter(key: str) -> Limiter:
    limiter = Limiter.select(key)
    if limiter is not None:
        return limiter

    return Limiter.create(key)


def maybe_limit_request() -> tuple[Limiter | None, ResponseReturnValue | None]:
    source = get_request_source()

    source_limiter = None

    authorization = request.headers.get("Authorization", None)
    if authorization is not None:
        token = ""
        if authorization.startswith("Bearer "):
            token = authorization[len("Bearer ") :]
        source_limiter = Limiter.select(f"token:{token}")
        if source_limiter is None:
            # We have an Authorization header that's not tied to any valid token
            # based limiter, which means the client is passing the wrong thing. 403
            # them so they know something needs fixed
            return (
                source_limiter,
                make_response(
                    {"err": -403, "msg": "forbidden"},
                    403,
                ),
            )

    authorized = source_limiter is not None
    authorized |= source.description in NO_LIMIT_UPSTREAMS

    # If we don't have a source_limiter based on the Authorization header,
    # default to one based on the remote address.
    if source_limiter is None:
        source_limiter = get_limiter(f"remote:{source.description}")
        user_agent = request.headers.get("User-Agent", "")
        if user_agent.lower().find("headlesschrome") >= 0:
            app.logger.info(
                f"HEADLESSCHROME: lowering params for: {source.description}"
            )
            source_limiter = source_limiter.set_parameters(3, 1.0 / 99.0)

    if DYNAMIC_RATE_LIMIT:
        source_ra = source_limiter.retry_after(1.0)
        if source_ra is not None:
            source_limiter.tick(0.200)
            source_ra = source_limiter.retry_after(1.0)
        if source_ra is not None:
            source_ra_v = math.ceil(source_ra + 1)
            app.logger.info(
                f"rate limiting {source.description}, retry after={source_ra_v}"
            )

            resp = make_response(
                {"err": -429, "msg": "too many requests", "retry_after": source_ra_v},
                429,
            )
            resp.headers["Retry-After"] = str(source_ra_v)
            return (source_limiter, resp)

        global_limiter = get_limiter("global")
        global_ra = global_limiter.retry_after(1.0)
        if global_ra is not None:
            global_ra_v = math.ceil(global_ra + 1)
            app.logger.info(f"rate limiting global, retry after={global_ra_v}")

            resp = make_response(
                {
                    "err": -429,
                    "msg": "too many requests (g)",
                    "retry_after": global_ra_v,
                },
                429,
            )
            resp.headers["Retry-After"] = str(global_ra_v)
            return (source_limiter, resp)

    # TODO: instead of blocking outright, insert ip into ip tag table and set
    # the limit to something much lower? Share a limit across azure/DO address
    # space?
    datacenter = ip_is_datacenter(source.description)

    # If we haven't seen a valid Authorization header, block anything that looks
    # like an autonomous network
    if datacenter is not None and not authorized:
        app.logger.info(f"BLOCKING DATACENTER IP: {datacenter} {source.description}")
        return (source_limiter, get_err(WebError.internal_datacenter))

    if datacenter is not None and authorized:
        app.logger.info(
            f"allowing datacenter ip, authorized: {datacenter} {source.description}"
        )

    if source.description in WEIRD_UPSTREAMS:
        app.logger.info(f"BLOCKING weird QQ: {source.description}")
        return (source_limiter, get_err(WebError.internal_strange))

    # TODO: both the testsuite and some annoying mass crawlers >_>
    automated = request.args.get("automated", None) == "true"
    if automated:
        app.logger.info(f"BLOCKING DATACENTER IP: automated=true {source.description}")
        return (source_limiter, get_err(WebError.internal_datacenter))

    return (source_limiter, None)


@app.route("/api/v0/epub", methods=["GET"])
def api_v0_epub() -> Any:
    source_limiter, limit_resp = maybe_limit_request()
    if limit_resp is not None:
        return limit_resp

    q = request.args.get("q", "").strip()
    url_id = request.args.get("id", "").strip()
    fixits = get_fixits(q)
    if len(q.strip()) < 1:
        return get_err(
            WebError.no_query,
            {
                "q": q,
                "fixits": fixits,
            },
        )

    app.logger.info(f"api_v0_epub: query: {q}")
    eres = ensure_export("epub", q, url_id)
    if "err" in eres:
        if DYNAMIC_RATE_LIMIT and source_limiter is not None:
            # TODO: maybe only do this when the fic is in the graveyard?
            source_limiter.tick(0.500)
        if "q" not in eres:
            eres["q"] = q
        if "fixits" not in eres:
            eres["fixits"] = fixits
        # fic was blacklisted by author
        # TODO: fix PLR2004 by finding corresponding constant
        if "ret" in eres and int(eres["ret"]) == 5 and "fixits" in eres:  # noqa: PLR2004
            eres.pop("fixits", None)
        return eres
    for key in ["epub_fname", "urlId", "url"]:
        if key not in eres:
            return get_err(
                WebError.ensure_failed,
                {
                    "key": key,
                    "msg": "please report this on discord",
                    "q": q,
                    "fixits": fixits,
                },
            )

    if FicBlacklist.check(eres["urlId"]):
        return get_err(WebError.greylisted)

    info = "[missing metadata; please report this on discord]"
    if "info" in eres:
        info = eres["info"]
    eh = eres["hash"] if "hash" in eres else str(random.getrandbits(32))

    res = {
        "q": q,
        "err": 0,
        "fixits": [],
        "info": info,
        "urlId": eres["urlId"],
    }
    res["urls"] = {"epub": eres["url"]}
    for key in ["meta", "slug", "hashes", "notes"]:
        if key in eres:
            res[key] = eres[key]

    # build auto-generating links for all formats
    for etype in ebook.EXPORT_TYPES:
        if etype == "epub":
            continue  # we already exported epub
        url = url_for(
            "get_cached_export_partial",
            etype=etype,
            url_id=eres["urlId"],
            cv=CACHE_BUSTER,
            eh=eh,
        )
        res[f"{etype}_url"] = url
        res["urls"][etype] = url

    # update epub url to direct download
    res["epub_url"] = eres["url"]

    return res


@app.route("/api/v0/meta", methods=["GET"])
def api_v0_meta() -> Any:
    q = request.args.get("q", "").strip()
    _url_id = request.args.get("id", "").strip()
    if len(q.strip()) < 1:
        return get_err(WebError.no_query, {"q": q})

    r = api_v0_epub()
    if not isinstance(r, dict):
        return r  # Rate limited 429
    if "meta" not in r:
        if "err" in r and isinstance(r["err"], int):
            return r
        return get_err(WebError.internal, {"q": q})
    return r["meta"]


@app.route("/legacy/epub_export", methods=["GET"])
def legacy_epub_export() -> ResponseReturnValue:
    res = api_v0_epub()
    if not isinstance(res, dict):
        # Rate limited 429
        q = request.args.get("q", "").strip()
        d = res.data.decode("utf-8")
        fixits = ["an error ocurred :(", "", markupsafe.escape(d)]
        return render_template("index.html", q=q, fixits=fixits, fic_info=None), 429
    q = request.args.get("q", "").strip() if "q" not in res else res["q"]
    fixits = res.get("fixits", [])
    if ("err" not in res or int(res["err"]) == 0) and "urlId" in res:
        return index_impl(res["urlId"], True)
    if "fixits" in res:
        del res["fixits"]
    fixits = ["an error ocurred :(", *fixits, "", markupsafe.escape(json.dumps(res))]
    return render_template("index.html", q=q, fixits=fixits, fic_info=None)


@app.route("/api/v0/remote", methods=["GET"])
def api_v0_remote() -> ResponseReturnValue:
    source = get_request_source()
    return source.__dict__


@app.context_processor
def inject_cache_buster() -> dict[str, str]:
    return {
        "CACHE_BUSTER": CACHE_BUSTER,
        "CURRENT_CSS": CURRENT_CSS,
        "JS_CACHE_BUSTER": JS_CACHE_BUSTER,
        "CSS_CACHE_BUSTER": CSS_CACHE_BUSTER,
        "NODE_NAME": NODE_NAME,
    }


@app.context_processor
def inject_suffix_info() -> dict[str, Any]:
    return {
        "EXPORT_SUFFIXES": ebook.EXPORT_SUFFIXES,
        "EXPORT_DESCRIPTIONS": ebook.EXPORT_DESCRIPTIONS,
    }


def uwsgi_init() -> None:
    global CSS_CACHE_BUSTER, JS_CACHE_BUSTER, CURRENT_CSS  # noqa: PLW0603

    CSS_CACHE_BUSTER = str(time.time())
    JS_CACHE_BUSTER = CSS_CACHE_BUSTER
    app.logger.info(f"reset JS/CSS CACHE_BUSTER: {JS_CACHE_BUSTER}")

    if Path("./static/style/_.css").is_file():
        with Path("./static/style/_.css").open() as f:
            CURRENT_CSS = f.read().strip()
        app.logger.info(f"reset CURRENT_CSS to len {len(CURRENT_CSS)}")

    if Path("./static/js/_.js").is_file():
        jshash = util.hash_file(Path("./static/js/_.js"))
        if len(jshash) > 0:
            JS_CACHE_BUSTER = jshash
        app.logger.info(f"reset JS_CACHE_BUSTER: {JS_CACHE_BUSTER}")

    app.logger.info("loading IP ranges")
    load_ip_ranges(Path("./dat/"), IP_TAG_SOURCES)
    for tag in TAGGED_IP_RANGES:
        app.logger.info(f"  loaded {tag=}: {len(TAGGED_IP_RANGES[tag])} IP ranges")


app.logger.info(__name__)

if __name__ == "__main__":
    app.run(debug=True)

if __name__ in {"uwsgi_file___main", "fichub_net.main"}:
    uwsgi_init()
