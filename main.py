from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Iterable,
    List,
    Optional,
    Tuple,
    Union,
    cast,
)
import contextlib
from enum import IntEnum
import json
import math
import os
import os.path
import random
import shutil
import time
import traceback

import flask
from flask import (
    Flask,
    Response,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.datastructures import Headers
from werkzeug.exceptions import NotFound

import ax
from db import FicBlacklist, FicInfo, RequestLog, RequestSource
import ebook
from ip_tag import TAGGED_IP_RANGES, ip_is_datacenter, load_ip_ranges
from limiter import Limiter
from rl_conf import (
    DYNAMIC_RATE_LIMIT,
    LIMIT_UPSTREAMS,
    LIMIT_UPSTREAMS_EXTRA,
    NO_LIMIT_UPSTREAMS,
    WEIRD_UPSTREAMS,
)

FlaskHeaderValue = Union[str, List[str], Tuple[str, ...]]
FlaskHeaders = Union[
    Headers, Dict[str, FlaskHeaderValue], List[Tuple[str, FlaskHeaderValue]]
]
BasicFlaskResponse = Union[Response, Any, Dict[str, Any], Generator[Any, None, None]]
FlaskResponse = Union[
    BasicFlaskResponse,
    Tuple[BasicFlaskResponse, FlaskHeaders],
    Tuple[BasicFlaskResponse, int],
    Tuple[BasicFlaskResponse, int, FlaskHeaders],
    Callable[[Dict[str, Any], BasicFlaskResponse], Iterable[bytes]],
]

app = Flask(__name__, static_url_path="")

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


errorMessages = {
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


def getErr(err: WebError, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = {"err": int(err), "msg": errorMessages[err]}
    if extra is not None:
        base.update(extra)
    return base


@app.errorhandler(404)
def page_not_found(_e: Exception) -> FlaskResponse:
    return render_template("404.html"), 404


@app.route("/api")
def api_landing() -> FlaskResponse:
    return render_template("api.html")


@app.route("/")
def index() -> FlaskResponse:
    urlId = request.args.get("id", "").strip()
    return index_impl(urlId, False)


def index_impl(urlId: str, legacy: bool) -> FlaskResponse:
    from_pw = request.args.get("from_pw", "").strip()

    blacklisted = False
    greylisted = False
    links = []
    ficInfo = None
    with contextlib.suppress(Exception):
        if legacy and len(urlId) > 1:
            fis = FicInfo.select(urlId)
            if len(fis) == 1:
                blacklisted = FicBlacklist.blacklisted(urlId)
                greylisted = FicBlacklist.greylisted(urlId)
                ficInfo = fis[0]

                epubRL = RequestLog.mostRecentByUrlId("epub", urlId)
                if epubRL is None:
                    # we always generate the epub first, so if we don't have it something went
                    # horribly wrong
                    raise Exception("uh oh")

                slug = ebook.buildFileSlug(ficInfo.title, ficInfo.author, urlId)
                eh = epubRL.exportFileHash
                if eh is None:
                    eh = "unknown"
                epubUrl = url_for(
                    "get_cached_export",
                    etype="epub",
                    urlId=urlId,
                    fname=f"{slug}.epub",
                    h=eh,
                )

                links = [("epub", True, epubUrl)]
                for etype in ebook.EXPORT_TYPES:
                    if etype == "epub":
                        continue
                    pe = ebook.findExistingExport(etype, urlId, eh)
                    if pe is None:
                        # for any etype that hasn't already been exported or is out of date,
                        # create a (re)generate link
                        link = url_for(
                            "get_cached_export_partial",
                            etype=etype,
                            urlId=urlId,
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
                            urlId=urlId,
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
            ficInfo=ficInfo,
            blacklisted=blacklisted,
            greylisted=greylisted,
            links=links,
        )
    )
    if legacy:
        resp.headers["X-Robots-Tag"] = "noindex"
    return resp


@app.route("/changes")
def changes() -> FlaskResponse:
    return redirect(url_for("index"))


@app.route("/fic/<urlId>")
def fic_info(urlId: str) -> FlaskResponse:
    allInfo = FicInfo.select(urlId)
    if len(allInfo) < 1:
        # entirely unknown fic, 404
        return page_not_found(NotFound())
    ficInfo = allInfo[0]

    return redirect(url_for("index", q=ficInfo.source, id=ficInfo.id))


@app.route("/cache/", defaults={"_page": 1})
@app.route("/cache/<int:_page>")
def cache_listing_deprecated(_page: int) -> FlaskResponse:
    return redirect(url_for("index"))


@app.route("/cache/today/", defaults={"_page": 1})
@app.route("/cache/today/<int:_page>")
def cache_listing_today(_page: int) -> FlaskResponse:
    return redirect(url_for("index"))


@app.route("/cache/<int:_year>/<int:_month>/<int:_day>/", defaults={"_page": 1})
@app.route("/cache/<int:_year>/<int:_month>/<int:_day>/<int:_page>")
def cache_listing(_year: int, _month: int, _day: int, _page: int) -> FlaskResponse:
    return redirect(url_for("index"))


@app.route("/popular/", defaults={"_page": 1})
@app.route("/popular/<int:_page>")
def popular_listing(_page: int) -> FlaskResponse:
    return render_template("popular_outmoded.html")


@app.route("/search/author/<_q>")
def search_author(_q: str) -> FlaskResponse:
    return redirect(url_for("index"))


def try_ensure_export(etype: str, urlId: str) -> Optional[str]:
    key = f"{etype}_fname"
    res = ensure_export(etype, urlId, urlId)
    if "err" in res or key not in res:
        return None
    if res[key] is None or isinstance(res[key], str):
        return cast(Optional[str], res[key])
    return None


class InvalidEtypeException(Exception):
    pass


def get_request_source() -> RequestSource:
    automated = request.args.get("automated", None) == "true"
    remote_addr = request.remote_addr
    if remote_addr is not None and remote_addr in TRUSTED_UPSTREAMS:
        remote_addr = request.headers.get("X-Forwarded-For", remote_addr)
    if remote_addr is None:
        remote_addr = "unknown"
    return RequestSource.upsert(automated, request.url_root, remote_addr)


def ensure_export(
    etype: str, query: str, urlId: Optional[str] = None
) -> Dict[str, Any]:
    print(f"ensure_export: query: {query}")
    if etype not in ebook.EXPORT_TYPES:
        return getErr(WebError.invalid_etype, {"fn": "ensure_export", "etype": etype})

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
            print(
                f"  limiting {source.description}: v={v:0.3} o={o:0.3} d={limit_d:0.3} ts={time.time()}"
            )
            time.sleep(limit_d)
        # time.sleep(.1)

    notes = []
    axAlive = ax.alive()
    if not axAlive:
        print("ensure_export: ax is not alive :(")
        if urlId is None or len(FicInfo.select(urlId)) != 1:
            return getErr(WebError.ax_dead)
        # otherwise fallthrough
        notes += ["backend api is down; results may be stale"]

    initTimeMs = int(time.time() * 1000)
    meta = None
    lres = None
    try:
        if not axAlive:
            meta = FicInfo.select(urlId)[0]
        else:
            lres = ax.lookup(query)
            if "err" in lres:
                endTimeMs = int(time.time() * 1000)
                RequestLog.insert(
                    source,
                    etype,
                    query,
                    endTimeMs - initTimeMs,
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
    except Exception as e:
        traceback.print_exc()
        print(e)
        print("ensure_export: ^ something went wrong doing ax.lookup :/")

        return getErr(WebError.lookup_failed)

    metaDict = meta.toJson()

    infoTimeMs = int(time.time() * 1000)
    infoRequestMs = infoTimeMs - initTimeMs

    # attempt to find previous epub export if it exists...
    try:
        existingEpub = None
        if meta.contentHash is not None:
            existingEpub = ebook.findExistingExport("epub", meta.id, meta.contentHash)

        existingExport = None
        if etype == "epub":
            existingExport = existingEpub
        elif existingEpub is not None:
            epub_fname, ehash = existingEpub
            existingExport = ebook.findExistingExport(etype, meta.id, ehash)

        if existingExport is not None:
            print(
                f"ensure_export({etype}, {query}): attempting to reuse previous export for {meta.id}"
            )
            fname, fhash = existingExport
            metaString = ebook.metaDataString(meta)

            slug = ebook.buildFileSlug(meta.title, meta.author, meta.id)
            suff = ebook.EXPORT_SUFFIXES[etype]
            exportUrl = url_for(
                "get_cached_export",
                etype=etype,
                urlId=meta.id,
                fname=f"{slug}{suff}",
                h=fhash,
            )

            endTimeMs = int(time.time() * 1000)
            exportMs = endTimeMs - infoTimeMs

            RequestLog.insert(
                source,
                etype,
                query,
                infoRequestMs,
                meta.id,
                json.dumps(lres),
                exportMs,
                fname,
                fhash,
                exportUrl,
            )

            print(
                f"ensure_export({etype}, {query}): reusing previous export for {meta.id}"
            )
            return {
                "urlId": meta.id,
                "info": metaString,
                f"{etype}_fname": fname,
                "hash": fhash,
                "url": exportUrl,
                "meta": metaDict,
                "slug": slug,
                "hashes": {etype: fhash},
                "notes": notes,
            }
    except Exception as e:
        traceback.print_exc()
        print(e)
        print(
            "ensure_export: ^ something went wrong trying to reuse existing export :/"
        )

    etext = None
    try:
        # TODO we could be timing this too...
        metaString = ebook.metaDataString(meta)
        chapters = ax.fetchChapters(meta)

        # actually do the export
        fname, fhash = "", ""
        if etype == "epub":
            fname, fhash = ebook.createEpub(meta, chapters)
        elif etype == "html":
            fname, fhash = ebook.createHtmlBundle(meta, chapters)
        elif etype in ["mobi", "pdf"]:
            fname, fhash = ebook.convertEpub(meta, chapters, etype)
        else:
            raise InvalidEtypeException(f"err: unknown etype: {etype}")

        slug = ebook.buildFileSlug(meta.title, meta.author, meta.id)
        suff = ebook.EXPORT_SUFFIXES[etype]
        exportUrl = url_for(
            "get_cached_export",
            etype=etype,
            urlId=meta.id,
            fname=f"{slug}{suff}",
            h=fhash,
        )

        endTimeMs = int(time.time() * 1000)
        exportMs = endTimeMs - infoTimeMs

        RequestLog.insert(
            source,
            etype,
            query,
            infoRequestMs,
            meta.id,
            json.dumps(lres),
            exportMs,
            fname,
            fhash,
            exportUrl,
        )

        return {
            "urlId": meta.id,
            "info": metaString,
            f"{etype}_fname": fname,
            "hash": fhash,
            "url": exportUrl,
            "meta": metaDict,
            "slug": slug,
            "hashes": {etype: fhash},
        }
    except Exception as e:
        endTimeMs = int(time.time() * 1000)
        exportMs = endTimeMs - infoTimeMs
        RequestLog.insert(
            source,
            etype,
            query,
            endTimeMs - initTimeMs,
            meta.id,
            json.dumps(lres),
            exportMs,
            None,
            None,
            None,
        )

        if (
            e.args is not None
            and len(e.args) > 0
            and isinstance(e, (ax.MissingChapterException, InvalidEtypeException))
        ):
            etext = e.args[0]

        traceback.print_exc()
        print(e)
        print("ensure_export: ^ something went wrong :/")

    return getErr(
        WebError.export_failed,
        {
            "msg": f"{etype} export failed\nplease try again in a few minutes, or report this on discord if the issue persists",
            "etext": etext,
            "meta": metaDict,
        },
    )


def legacy_cache_redirect(etype: str, fname: str) -> FlaskResponse:
    fhash = request.args.get("h", None)
    urlId = fname
    if urlId.find("-") >= 0:
        urlId = urlId.split("-")[-1]
    suff = ebook.EXPORT_SUFFIXES[etype]
    if urlId.endswith(suff):
        urlId = urlId[: -len(suff)]
    if fhash is None:
        return redirect(
            url_for(
                "get_cached_export_partial", etype=etype, urlId=urlId, cv=CACHE_BUSTER
            )
        )
    return redirect(
        url_for(
            "get_cached_export",
            etype=etype,
            urlId=urlId,
            fname=f"{fhash}{suff}",
            cv=CACHE_BUSTER,
        )
    )


@app.route("/epub/<fname>")
def get_cached_epub_v0(fname: str) -> FlaskResponse:
    return legacy_cache_redirect("epub", fname)


@app.route("/html/<fname>")
def get_cached_html_v0(fname: str) -> FlaskResponse:
    return legacy_cache_redirect("html", fname)


@app.route("/cache/<etype>/<urlId>/<fname>")
def get_cached_export(etype: str, urlId: str, fname: str) -> FlaskResponse:
    if etype not in ebook.EXPORT_TYPES:
        # if this is an unsupported export type, 404
        return page_not_found(NotFound())

    mimetype = ebook.EXPORT_MIMETYPES[etype]
    suff = ebook.EXPORT_SUFFIXES[etype]
    if not fname.endswith(suff):
        # we have a request for the wrong extension, 404
        return page_not_found(NotFound())

    source_limiter, limit_resp = maybe_limit_request()
    if limit_resp is not None:
        return limit_resp

    if FicBlacklist.check(urlId):
        # blacklisted fic, 404
        return render_template("fic_info_blacklist.html"), 404

    fhash = request.args.get("h", None)
    fdir, sfdir = ebook.buildExportPath(etype, urlId)
    if fhash is not None:
        # if the request is for a specific slug, try to serve it directly
        rname = fname
        fname = f"{fhash}{suff}"
        if not os.path.isfile(os.path.join(fdir, fname)) and os.path.isfile(
            os.path.join(sfdir, fname)
        ):
            os.makedirs(fdir)
            shutil.move(os.path.join(sfdir, fname), os.path.join(fdir, fname))
        if os.path.isfile(os.path.join(fdir, fname)):
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
    allInfo = FicInfo.select(urlId)
    if len(allInfo) < 1:
        # entirely unknown fic, 404
        return page_not_found(NotFound())
    ficInfo = allInfo[0]
    slug = ebook.buildFileSlug(ficInfo.title, ficInfo.author, urlId)
    rl = RequestLog.mostRecentByUrlId(etype, urlId)
    if rl is None:
        return page_not_found(NotFound())

    if not os.path.isfile(os.path.join(fdir, f"{rl.exportFileHash}{suff}")):
        # the most recent export is missing for some reason... regenerate it
        return get_cached_export_partial(etype, urlId)

    # redirect back to ourself with the correct filename
    return redirect(
        url_for(
            "get_cached_export",
            etype=etype,
            urlId=urlId,
            fname=f"{slug}{suff}",
            h=rl.exportFileHash,
        )
    )


@app.route("/cache/<etype>/<urlId>")
def get_cached_export_partial(etype: str, urlId: str) -> Any:
    if etype not in ebook.EXPORT_TYPES:
        # if this is an unsupported export type, 404
        return page_not_found(NotFound())

    # otherwise we have a urlId we need to export
    fname = try_ensure_export(etype, urlId)
    if fname is None:
        # if we failed to generate the export, 503
        return render_template("503_janus.html"), 503

    return get_cached_export(etype, urlId, fname)


def get_fixits(q: str) -> List[str]:
    fixits: List[str] = []
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
        import es

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


def maybe_limit_request() -> Tuple[Optional[Limiter], Any]:
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
            print(f"HEADLESSCHROME: lowering params for: {source.description}")
            source_limiter = source_limiter.set_parameters(3, 1.0 / 99.0)

    if DYNAMIC_RATE_LIMIT:
        source_ra = source_limiter.retryAfter(1.0)
        if source_ra is not None:
            source_limiter.tick(0.200)
            source_ra = source_limiter.retryAfter(1.0)
        if source_ra is not None:
            source_ra_v = int(math.ceil(source_ra + 1))
            print(f"rate limiting {source.description}, retry after={source_ra_v}")

            resp = make_response(
                {"err": -429, "msg": "too many requests", "retry_after": source_ra_v},
                429,
            )
            resp.headers["Retry-After"] = str(source_ra_v)
            return (source_limiter, resp)

        global_limiter = get_limiter("global")
        global_ra = global_limiter.retryAfter(1.0)
        if global_ra is not None:
            global_ra_v = int(math.ceil(global_ra + 1))
            print(f"rate limiting global, retry after={global_ra_v}")

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

    # TODO instead of blocking outright, insert ip into ip tag table and set the
    # limit to something much lower? Share a limit across azure/DO address
    # space?
    datacenter = ip_is_datacenter(source.description)

    # If we haven't seen a valid Authorization header, block anything that looks
    # like an autonomous network
    if datacenter is not None and not authorized:
        print(f"BLOCKING DATACENTER IP: {datacenter} {source.description}")
        return (source_limiter, getErr(WebError.internal_datacenter))

    if datacenter is not None and authorized:
        print(f"allowing datacenter ip, authorized: {datacenter} {source.description}")

    if source.description in WEIRD_UPSTREAMS:
        print(f"BLOCKING weird QQ: {source.description}")
        return (source_limiter, getErr(WebError.internal_strange))

    # TODO both the testsuite and some annoying mass crawlers >_>
    automated = request.args.get("automated", None) == "true"
    if automated:
        print(f"BLOCKING DATACENTER IP: automated=true {source.description}")
        return (source_limiter, getErr(WebError.internal_datacenter))

    return (source_limiter, None)


@app.route("/api/v0/epub", methods=["GET"])
def api_v0_epub() -> Any:
    source_limiter, limit_resp = maybe_limit_request()
    if limit_resp is not None:
        return limit_resp

    q = request.args.get("q", "").strip()
    urlId = request.args.get("id", "").strip()
    fixits = get_fixits(q)
    if len(q.strip()) < 1:
        return getErr(
            WebError.no_query,
            {
                "q": q,
                "fixits": fixits,
            },
        )

    print(f"api_v0_epub: query: {q}")
    eres = ensure_export("epub", q, urlId)
    if "err" in eres:
        if DYNAMIC_RATE_LIMIT and source_limiter is not None:
            # TODO maybe only do this when the fic is in the graveyard?
            source_limiter.tick(0.500)
        if "q" not in eres:
            eres["q"] = q
        if "fixits" not in eres:
            eres["fixits"] = fixits
        # fic was blacklisted by author
        if "ret" in eres and int(eres["ret"]) == 5 and "fixits" in eres:
            eres.pop("fixits", None)
        return eres
    for key in ["epub_fname", "urlId", "url"]:
        if key not in eres:
            return getErr(
                WebError.ensure_failed,
                {
                    "key": key,
                    "msg": "please report this on discord",
                    "q": q,
                    "fixits": fixits,
                },
            )

    if FicBlacklist.check(eres["urlId"]):
        return getErr(WebError.greylisted)

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
            urlId=eres["urlId"],
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
    _urlId = request.args.get("id", "").strip()
    if len(q.strip()) < 1:
        return getErr(WebError.no_query, {"q": q})

    r = api_v0_epub()
    if not isinstance(r, dict):
        return r  # Rate limited 429
    if "meta" not in r:
        if "err" in r and isinstance(r["err"], int):
            return r
        return getErr(WebError.internal, {"q": q})
    return r["meta"]


@app.route("/legacy/epub_export", methods=["GET"])
def legacy_epub_export() -> FlaskResponse:
    res = api_v0_epub()
    if not isinstance(res, dict):
        # Rate limited 429
        q = request.args.get("q", "").strip()
        d = res.data.decode("utf-8")
        fixits = ["an error ocurred :("] + ["", flask.escape(d)]
        return render_template("index.html", q=q, fixits=fixits, ficInfo=None), 429
    q = request.args.get("q", "").strip() if "q" not in res else res["q"]
    fixits = res.get("fixits", [])
    if "err" not in res or int(res["err"]) == 0 and "urlId" in res:
        return index_impl(res["urlId"], True)
        # return redirect(url_for('index', q=q, id=res['urlId'], noscript='true'))
        # return redirect(url_for('fic_info', urlId=res['urlId']))
    if "fixits" in res:
        del res["fixits"]
    fixits = ["an error ocurred :("] + fixits + ["", flask.escape(json.dumps(res))]
    return render_template("index.html", q=q, fixits=fixits, ficInfo=None)


@app.route("/api/v0/remote", methods=["GET"])
def api_v0_remote() -> FlaskResponse:
    source = get_request_source()
    return source.__dict__


@app.context_processor
def inject_cache_buster() -> Dict[str, str]:
    return {
        "CACHE_BUSTER": CACHE_BUSTER,
        "CURRENT_CSS": CURRENT_CSS,
        "JS_CACHE_BUSTER": JS_CACHE_BUSTER,
        "CSS_CACHE_BUSTER": CSS_CACHE_BUSTER,
        "NODE_NAME": NODE_NAME,
    }


@app.context_processor
def inject_suffix_info() -> Dict[str, Any]:
    return {
        "EXPORT_SUFFIXES": ebook.EXPORT_SUFFIXES,
        "EXPORT_DESCRIPTIONS": ebook.EXPORT_DESCRIPTIONS,
    }


def uwsgi_init() -> None:
    global CSS_CACHE_BUSTER, JS_CACHE_BUSTER, CURRENT_CSS

    CSS_CACHE_BUSTER = str(time.time())
    JS_CACHE_BUSTER = CSS_CACHE_BUSTER
    print(f"reset JS/CSS CACHE_BUSTER: {JS_CACHE_BUSTER}")

    if os.path.isfile("./static/style/_.css"):
        with open("./static/style/_.css") as f:
            CURRENT_CSS = f.read().strip()
        print(f"reset CURRENT_CSS to len {len(CURRENT_CSS)}")

    if os.path.isfile("./static/js/_.js"):
        import util

        jshash = util.hashFile("./static/js/_.js")
        if len(jshash) == 32:
            JS_CACHE_BUSTER = jshash
        print(f"reset JS_CACHE_BUSTER: {JS_CACHE_BUSTER}")
    print()

    print("loading IP ranges")
    load_ip_ranges()
    for tag in TAGGED_IP_RANGES:
        print(f"  loaded {tag=}: {len(TAGGED_IP_RANGES[tag])} IP ranges")


print()
print(__name__)

if __name__ == "__main__":
    app.run(debug=True)

if __name__ == "uwsgi_file___main":
    uwsgi_init()
