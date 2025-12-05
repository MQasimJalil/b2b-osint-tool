import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Discovery from './pages/Discovery';
import Companies from './pages/Companies';
import CompanyDetail from './pages/CompanyDetail';
import KnowledgeBase from './pages/KnowledgeBase';
import EmailCenter from './pages/EmailCenter';
import DraftEditor from './pages/DraftEditor';
import Login from './pages/Login';
import NotFound from './pages/NotFound';

function App() {
  return (
    <Router>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<Login />} />

        {/* Protected routes */}
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="discovery" element={<Discovery />} />
          <Route path="companies" element={<Companies />} />
          <Route path="companies/:domain" element={<CompanyDetail />} />
          <Route path="knowledge-base" element={<KnowledgeBase />} />
          <Route path="email" element={<EmailCenter />} />
          <Route path="email/:campaignId/draft/:draftId" element={<DraftEditor />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
