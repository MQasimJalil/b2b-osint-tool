import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Building2, Mail, Search, TrendingUp, Activity, CheckCircle } from 'lucide-react';
import { api } from '../api/client';

export default function Dashboard() {
  const [stats, setStats] = useState({
    totalCompanies: 0,
    companiesWithContacts: 0,
    totalContacts: 0,
    emailsSent: 0,
  });
  const [recentCompanies, setRecentCompanies] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);

      // Load stats from dedicated endpoint
      const statsRes = await api.companies.stats();
      const statsData = statsRes.data || {};
      setStats({
        totalCompanies: statsData.total_companies || 0,
        companiesWithContacts: statsData.companies_with_contacts || 0,
        totalContacts: statsData.total_contacts || 0,
        emailsSent: statsData.emails_sent || 0,
      });

      // Load recent companies for display
      const companiesRes = await api.companies.list({ limit: 5 });
      const companies = companiesRes.data?.companies || [];
      setRecentCompanies(companies);
    } catch (error) {
      console.error('Failed to load dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  const statCards = [
    {
      name: 'Total Companies',
      value: stats.totalCompanies,
      icon: Building2,
      color: 'bg-blue-500',
      change: '+12%',
    },
    {
      name: 'Companies with Contacts',
      value: stats.companiesWithContacts,
      icon: CheckCircle,
      color: 'bg-green-500',
      change: '+8%',
    },
    {
      name: 'Total Contacts',
      value: stats.totalContacts,
      icon: Mail,
      color: 'bg-purple-500',
      change: '+23%',
    },
    {
      name: 'Emails Sent',
      value: stats.emailsSent,
      icon: TrendingUp,
      color: 'bg-orange-500',
      change: '+15%',
    },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500">
          Welcome back! Here's what's happening with your B2B data.
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map((stat) => (
          <div
            key={stat.name}
            className="relative overflow-hidden bg-white rounded-lg border border-gray-200 p-6"
          >
            <div className="flex items-center">
              <div className={`${stat.color} p-3 rounded-lg`}>
                <stat.icon className="w-6 h-6 text-white" />
              </div>
              <div className="ml-4 flex-1">
                <p className="text-sm font-medium text-gray-500">{stat.name}</p>
                <div className="flex items-baseline">
                  <p className="text-2xl font-semibold text-gray-900">{stat.value}</p>
                  <span className="ml-2 text-sm font-medium text-green-600">{stat.change}</span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Recent Companies */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Recent Companies</h2>
            <Link
              to="/companies"
              className="text-sm font-medium text-blue-600 hover:text-blue-700"
            >
              View all
            </Link>
          </div>
          <div className="space-y-4">
            {recentCompanies.length === 0 ? (
              <p className="text-sm text-gray-500">No companies yet. Start by running discovery!</p>
            ) : (
              recentCompanies.slice(0, 5).map((company) => (
                <Link
                  key={company.id}
                  to={`/companies/${company.id}`}
                  className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center">
                    <Building2 className="w-5 h-5 text-gray-400 mr-3" />
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        {company.company_name || company.domain}
                      </p>
                      <p className="text-xs text-gray-500">{company.domain}</p>
                    </div>
                  </div>
                  {company.contact_score && (
                    <span className="text-xs px-2 py-1 bg-green-100 text-green-800 rounded-full">
                      {company.contact_score} contacts
                    </span>
                  )}
                </Link>
              ))
            )}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="bg-white rounded-lg border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
          <div className="space-y-3">
            <Link
              to="/discovery"
              className="flex items-center p-4 rounded-lg border-2 border-dashed border-gray-300 hover:border-blue-500 hover:bg-blue-50 transition-colors"
            >
              <Search className="w-6 h-6 text-blue-600 mr-3" />
              <div>
                <p className="text-sm font-medium text-gray-900">Discover Companies</p>
                <p className="text-xs text-gray-500">Find new B2B opportunities</p>
              </div>
            </Link>
            <Link
              to="/email"
              className="flex items-center p-4 rounded-lg border-2 border-dashed border-gray-300 hover:border-purple-500 hover:bg-purple-50 transition-colors"
            >
              <Mail className="w-6 h-6 text-purple-600 mr-3" />
              <div>
                <p className="text-sm font-medium text-gray-900">Email Center</p>
                <p className="text-xs text-gray-500">Verify and send emails</p>
              </div>
            </Link>
            <Link
              to="/companies"
              className="flex items-center p-4 rounded-lg border-2 border-dashed border-gray-300 hover:border-green-500 hover:bg-green-50 transition-colors"
            >
              <Building2 className="w-6 h-6 text-green-600 mr-3" />
              <div>
                <p className="text-sm font-medium text-gray-900">View Companies</p>
                <p className="text-xs text-gray-500">Browse your company database</p>
              </div>
            </Link>
          </div>
        </div>
      </div>

      {/* Activity Feed - Placeholder for future */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Recent Activity</h2>
          <Activity className="w-5 h-5 text-gray-400" />
        </div>
        <div className="text-center py-8 text-gray-500">
          <Activity className="w-12 h-12 mx-auto mb-3 text-gray-300" />
          <p className="text-sm">No recent activity</p>
        </div>
      </div>
    </div>
  );
}
