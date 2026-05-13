"""API router aggregator. Health is real (Batch 0); the other 28 are stubs activated batch-by-batch."""
from fastapi import APIRouter

from . import (
    audit,
    auth,
    benchmarks,
    catalogue,
    chat,
    client_journeys,
    diffs,
    digest,
    eval as _eval,
    exports,
    flags,
    graph,
    health,
    lens,
    lifecycle,
    news,
    notifications,
    personas,
    projects,
    reasoning_chains,
    search,
    settings as _settings,
    sheets,
    sows,
    stories,
    suggestions,
    trends,
    validation_gates,
    vendor_intel,
    versions,
    what_if,
)

api_router = APIRouter()

# Real
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# Stubs — each batch lights its own routes up
api_router.include_router(catalogue.router, prefix="/catalogue", tags=["catalogue"])
api_router.include_router(lens.router, prefix="/lens", tags=["lens"])
api_router.include_router(versions.router, prefix="/versions", tags=["versions"])
api_router.include_router(diffs.router, prefix="/diffs", tags=["diffs"])
api_router.include_router(flags.router, prefix="/flags", tags=["flags"])
api_router.include_router(suggestions.router, prefix="/suggestions", tags=["suggestions"])
api_router.include_router(trends.router, prefix="/trends", tags=["trends"])
api_router.include_router(news.router, prefix="/news", tags=["news"])
api_router.include_router(sows.router, prefix="/sows", tags=["sows"])
api_router.include_router(stories.router, prefix="/stories", tags=["stories"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(benchmarks.router, prefix="/benchmarks", tags=["benchmarks"])
api_router.include_router(lifecycle.router, prefix="/lifecycle", tags=["lifecycle"])
api_router.include_router(vendor_intel.router, prefix="/vendor-intel", tags=["vendor-intel"])
api_router.include_router(client_journeys.router, prefix="/clients", tags=["clients"])
api_router.include_router(digest.router, prefix="/digest", tags=["digest"])
api_router.include_router(graph.router, prefix="/graph", tags=["graph"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(validation_gates.router, prefix="/validation-gates", tags=["validation-gates"])
api_router.include_router(reasoning_chains.router, prefix="/reasoning-chains", tags=["reasoning-chains"])
api_router.include_router(sheets.router, prefix="/sheets", tags=["sheets"])
api_router.include_router(_settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(_eval.router, prefix="/eval", tags=["eval"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(exports.router, prefix="/exports", tags=["exports"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(personas.router, prefix="/personas", tags=["personas"])
api_router.include_router(what_if.router, prefix="/what-if", tags=["what-if"])
