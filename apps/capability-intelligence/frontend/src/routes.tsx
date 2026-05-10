import { Route, Routes } from 'react-router-dom';
import MissionControl from './pages/MissionControl';
import CapabilityExplorer from './pages/CapabilityExplorer';
import SubcapDeepDive from './pages/SubcapDeepDive';
import ValueChainAtlas from './pages/ValueChainAtlas';
import SubverticalCompare from './pages/SubverticalCompare';
import PlatformCatalog from './pages/PlatformCatalog';
import UseCaseExplorer from './pages/UseCaseExplorer';
import MaturityHeatmap from './pages/MaturityHeatmap';
import KnowledgeGraph from './pages/KnowledgeGraph';
import SowLibrary from './pages/SowLibrary';
import StoryLibrary from './pages/StoryLibrary';
import ProjectSubcapTrace from './pages/ProjectSubcapTrace';
import NewsWatch from './pages/NewsWatch';
import TrendsMonitor from './pages/TrendsMonitor';
import AiSuggestions from './pages/AiSuggestions';
import BenchmarksStudio from './pages/BenchmarksStudio';
import StrategicDigest from './pages/StrategicDigest';
import LifecycleManager from './pages/LifecycleManager';
import VendorIntelligence from './pages/VendorIntelligence';
import ClientJourneyAtlas from './pages/ClientJourneyAtlas';
import VersionTimeline from './pages/VersionTimeline';
import DiffViewer from './pages/DiffViewer';
import ChangeFlagsInbox from './pages/ChangeFlagsInbox';
import ValidationGatesLog from './pages/ValidationGatesLog';
import QaAuditDashboard from './pages/QaAuditDashboard';
import ReasoningChainViewer from './pages/ReasoningChainViewer';
import AiChat from './pages/AiChat';
import WhatIfSimulator from './pages/WhatIfSimulator';

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<MissionControl />} />
      <Route path="/explorer" element={<CapabilityExplorer />} />
      <Route path="/subcap" element={<SubcapDeepDive />} />
      <Route path="/value-chain" element={<ValueChainAtlas />} />
      <Route path="/subvertical-compare" element={<SubverticalCompare />} />
      <Route path="/platforms" element={<PlatformCatalog />} />
      <Route path="/use-cases" element={<UseCaseExplorer />} />
      <Route path="/maturity" element={<MaturityHeatmap />} />
      <Route path="/graph" element={<KnowledgeGraph />} />
      <Route path="/sows" element={<SowLibrary />} />
      <Route path="/stories" element={<StoryLibrary />} />
      <Route path="/trace" element={<ProjectSubcapTrace />} />
      <Route path="/news" element={<NewsWatch />} />
      <Route path="/trends" element={<TrendsMonitor />} />
      <Route path="/suggestions" element={<AiSuggestions />} />
      <Route path="/benchmarks" element={<BenchmarksStudio />} />
      <Route path="/digest" element={<StrategicDigest />} />
      <Route path="/lifecycle" element={<LifecycleManager />} />
      <Route path="/vendors" element={<VendorIntelligence />} />
      <Route path="/clients" element={<ClientJourneyAtlas />} />
      <Route path="/versions" element={<VersionTimeline />} />
      <Route path="/diff" element={<DiffViewer />} />
      <Route path="/flags" element={<ChangeFlagsInbox />} />
      <Route path="/validation-gates" element={<ValidationGatesLog />} />
      <Route path="/audit" element={<QaAuditDashboard />} />
      <Route path="/reasoning" element={<ReasoningChainViewer />} />
      <Route path="/chat" element={<AiChat />} />
      <Route path="/what-if" element={<WhatIfSimulator />} />
    </Routes>
  );
}
