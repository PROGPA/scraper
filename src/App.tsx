import { useState, useEffect, useRef, useCallback } from 'react';
import { Search, Download, Trash2, Loader2, PlayCircle, StopCircle, Clock, CheckCircle, XCircle, User } from 'lucide-react';
import { Button } from './components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './components/ui/card';
import { Textarea } from './components/ui/textarea';
import { Badge } from './components/ui/badge';
import { Progress } from './components/ui/progress';
import { ScrollArea } from './components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from './components/ui/dialog';
import { Input } from './components/ui/input';
import { Label } from './components/ui/label';
import { toast } from 'sonner@2.0.3';
import { Toaster } from './components/ui/sonner';

interface JobResult {
  [url: string]: string[];
}

interface Job {
  id: string;
  status: 'queued' | 'running' | 'finished' | 'failed' | 'cancelled';
  created_at: string;
  updated_at: string;
  count: number;
  results?: JobResult;
  progress?: {
    done: number;
    total: number;
    current?: string;
  };
}

interface UserInfo {
  id: string;
  name: string;
  createdAt: string;
}

export default function App() {
  const [urls, setUrls] = useState('');
  const [jobs, setJobs] = useState<Job[]>([]);
  const [currentJob, setCurrentJob] = useState<Job | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [showNameDialog, setShowNameDialog] = useState(false);
  const [userName, setUserName] = useState('');
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [backendAvailable, setBackendAvailable] = useState<boolean | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Dynamic backend URL based on environment
  const getBackendUrl = useCallback(() => {
    // Check if running in development (localhost) or production
    const isDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    if (isDev) {
      return 'http://localhost:8000';
    }
    // In production, assume backend is on same host with different port or path
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }, []);

  const connectWebSocket = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const backendHost = window.location.hostname;
    const wsUrl = `${protocol}//${backendHost}:8000/ws`;
    
    try {
      const ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        setWsConnected(true);
        setBackendAvailable(true);
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = null;
        }
        toast.success('Connected to scraper backend');
      };
      
      ws.onclose = () => {
        setWsConnected(false);
        // Don't spam reconnect attempts
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
        }
        reconnectTimeoutRef.current = setTimeout(() => {
          if (wsRef.current === ws) {
            console.log('Attempting to reconnect...');
            connectWebSocket();
          }
        }, 5000);
      };
      
      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setBackendAvailable(false);
      };
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        switch (data.type) {
          case 'job_created':
            setCurrentJob({
              id: data.job_id,
              status: 'queued',
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              count: data.count,
              progress: { done: 0, total: data.count }
            });
            toast.success(`Job created: ${data.count} URLs`);
            break;
            
          case 'progress':
            setCurrentJob(prev => prev?.id === data.job_id ? {
              ...prev,
              status: 'running',
              updated_at: new Date().toISOString(),
              progress: {
                done: data.done,
                total: data.total,
                current: data.current
              },
              results: {
                ...prev.results,
                [data.current]: data.emails
              }
            } : prev);
            break;
            
          case 'finished':
            setCurrentJob(prev => {
              if (prev?.id === data.job_id) {
                // Notify dashboard of completion with user info (non-blocking)
                if (userInfo) {
                  const totalEmails = Object.values(data.results || {}).reduce(
                    (sum: number, emails: string[]) => sum + emails.length, 
                    0
                  );
                  
                  syncToDashboard({
                    action: 'job_completed',
                    job_id: data.job_id,
                    user_id: userInfo.id,
                    user_name: userInfo.name,
                    total_emails: totalEmails,
                    url_count: Object.keys(data.results || {}).length,
                    timestamp: new Date().toISOString(),
                  });
                }
                
                return {
                  ...prev,
                  status: 'finished',
                  updated_at: new Date().toISOString(),
                  results: data.results
                };
              }
              return prev;
            });
            toast.success('Scraping completed!');
            fetchJobs();
            break;
            
          case 'cancelled':
            setCurrentJob(prev => prev?.id === data.job_id ? {
              ...prev,
              status: 'cancelled',
              updated_at: new Date().toISOString()
            } : prev);
            toast.info('Job cancelled');
            break;
            
          case 'error':
            toast.error(data.msg || 'An error occurred');
            if (data.job_id) {
              setCurrentJob(prev => prev?.id === data.job_id ? {
                ...prev,
                status: 'failed',
                updated_at: new Date().toISOString()
              } : prev);
            }
            break;
        }
      } catch (err) {
        console.error('Failed to parse message:', err);
      }
    };
    
      wsRef.current = ws;
      return ws;
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      setBackendAvailable(false);
      return null;
    }
  }, [userInfo]);

  // Check for existing user on mount
  useEffect(() => {
    const storedUser = localStorage.getItem('emailScraperUser');
    if (storedUser) {
      try {
        const user = JSON.parse(storedUser);
        setUserInfo(user);
        toast.success(`Welcome back, ${user.name}!`);
      } catch (err) {
        // Invalid stored data, show dialog
        setShowNameDialog(true);
      }
    } else {
      // First time user
      setShowNameDialog(true);
    }
  }, []);

  // Check backend availability on mount
  useEffect(() => {
    const checkBackend = async () => {
      try {
        const backendUrl = getBackendUrl();
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 3000);
        
        const response = await fetch(`${backendUrl}/health`, {
          signal: controller.signal,
        });
        
        clearTimeout(timeoutId);
        
        if (response.ok) {
          setBackendAvailable(true);
        } else {
          setBackendAvailable(false);
        }
      } catch (err) {
        setBackendAvailable(false);
        console.warn('Backend not available. Make sure the Python backend is running on port 8000.');
      }
    };
    
    checkBackend();
  }, [getBackendUrl]);

  useEffect(() => {
    // Only try to connect if backend is available
    if (backendAvailable === true) {
      const ws = connectWebSocket();
      return () => {
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
        }
        if (ws) {
          ws.close();
        }
      };
    }
  }, [connectWebSocket, backendAvailable]);

  const fetchJobs = async () => {
    try {
      const backendUrl = getBackendUrl();
      const response = await fetch(`${backendUrl}/jobs`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      const data = await response.json();
      setJobs(data.reverse());
    } catch (err) {
      console.error('Failed to fetch jobs:', err);
      // Don't show error toast on initial load - backend might not be ready yet
    }
  };

  useEffect(() => {
    // Fetch jobs once backend is confirmed available
    if (backendAvailable === true) {
      fetchJobs();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendAvailable]);

  const generateUserId = () => {
    return `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  };

  const syncToDashboard = async (payload: any) => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout
      
      const response = await fetch('https://royalblue-goldfish-140935.hostingersite.com/api.php', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          secret_key: 'scraper_sync_123',
          ...payload,
        }),
        signal: controller.signal,
      });
      
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        console.warn(`Dashboard sync failed: HTTP ${response.status}`);
      }
    } catch (err) {
      // Silently fail - dashboard sync is optional
      if (err instanceof Error && err.name !== 'AbortError') {
        console.warn('Dashboard sync skipped:', err.message);
      }
    }
  };

  const handleUserRegistration = async () => {
    if (!userName.trim()) {
      toast.error('Please enter your name');
      return;
    }

    const isUpdate = userInfo !== null;
    const userId = userInfo?.id || generateUserId();

    const updatedUser: UserInfo = {
      id: userId,
      name: userName.trim(),
      createdAt: userInfo?.createdAt || new Date().toISOString(),
    };

    // Store locally first
    localStorage.setItem('emailScraperUser', JSON.stringify(updatedUser));
    setUserInfo(updatedUser);
    setShowNameDialog(false);
    setUserName('');
    
    toast.success(isUpdate ? `Name updated to ${updatedUser.name}` : `Welcome, ${updatedUser.name}! You can now start scraping.`);

    // Optionally sync to dashboard (non-blocking)
    syncToDashboard({
      action: isUpdate ? 'update_user' : 'register_user',
      user: updatedUser,
    });
  };

  const handleEditProfile = () => {
    if (userInfo) {
      setUserName(userInfo.name);
    }
    setShowNameDialog(true);
  };

  const startScraping = () => {
    if (!urls.trim()) {
      toast.error('Please enter at least one URL');
      return;
    }

    if (!userInfo) {
      toast.error('User information not found');
      setShowNameDialog(true);
      return;
    }
    
    if (!wsRef.current || !wsConnected) {
      toast.error('Backend not connected. Please wait or check if the Python server is running.');
      return;
    }
    
    const urlList = urls.split('\n').filter(u => u.trim());
    
    wsRef.current.send('start' + JSON.stringify(urlList));
    setUrls('');

    // Optionally notify dashboard that job is starting (non-blocking)
    syncToDashboard({
      action: 'job_started',
      user_id: userInfo.id,
      user_name: userInfo.name,
      url_count: urlList.length,
      timestamp: new Date().toISOString(),
    });
  };

  const cancelJob = () => {
    if (currentJob && wsRef.current && wsConnected) {
      wsRef.current.send('cancel' + currentJob.id);
    }
  };

  const exportToCSV = (results: JobResult) => {
    const rows: string[][] = [['URL', 'Email Addresses']];
    
    Object.entries(results).forEach(([url, emails]) => {
      rows.push([url, emails.join(', ')]);
    });
    
    const csv = rows.map(row => 
      row.map(cell => `"${cell.replace(/"/g, '""')}"`).join(',')
    ).join('\n');
    
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `emails_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Exported to CSV');
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
        return <Loader2 className="w-4 h-4 animate-spin" />;
      case 'finished':
        return <CheckCircle className="w-4 h-4" />;
      case 'failed':
        return <XCircle className="w-4 h-4" />;
      case 'cancelled':
        return <StopCircle className="w-4 h-4" />;
      default:
        return <Clock className="w-4 h-4" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'default';
      case 'finished':
        return 'default';
      case 'failed':
        return 'destructive';
      case 'cancelled':
        return 'secondary';
      default:
        return 'outline';
    }
  };

  const totalEmails = currentJob?.results 
    ? Object.values(currentJob.results).reduce((sum, emails) => sum + emails.length, 0)
    : 0;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-4 md:p-8">
      <Toaster />
      
      {/* User Registration Dialog */}
      <Dialog open={showNameDialog} onOpenChange={(open) => {
        // Prevent closing if no user is registered yet
        if (!open && !userInfo) return;
        setShowNameDialog(open);
        if (!open) setUserName('');
      }}>
        <DialogContent className="sm:max-w-md" onPointerDownOutside={(e) => {
          // Prevent closing on outside click if no user registered
          if (!userInfo) e.preventDefault();
        }}>
          <DialogHeader>
            <DialogTitle>{userInfo ? 'Update Your Name' : 'Welcome to Email Scraper'}</DialogTitle>
            <DialogDescription>
              {userInfo 
                ? 'Update your name for the dashboard.'
                : 'Please enter your name to get started. This helps us manage users on our dashboard.'
              }
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name">Your Name</Label>
              <Input
                id="name"
                placeholder="Enter your full name"
                value={userName}
                onChange={(e) => setUserName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    handleUserRegistration();
                  }
                }}
                autoFocus
              />
            </div>
            {userInfo && (
              <div className="text-slate-500 p-3 bg-slate-50 rounded-md space-y-1">
                <p className="flex items-center gap-2">
                  <span>User ID:</span>
                  <span className="font-mono text-slate-700">{userInfo.id}</span>
                </p>
                <p className="flex items-center gap-2">
                  <span>Registered:</span>
                  <span className="text-slate-700">{new Date(userInfo.createdAt).toLocaleDateString()}</span>
                </p>
              </div>
            )}
          </div>
          <DialogFooter className="gap-2">
            {userInfo && (
              <Button 
                variant="outline" 
                onClick={() => {
                  setShowNameDialog(false);
                  setUserName('');
                }}
                className="flex-1"
              >
                Cancel
              </Button>
            )}
            <Button onClick={handleUserRegistration} className="flex-1">
              {userInfo ? 'Update' : 'Continue'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-slate-900">Email Scraper</h1>
          <p className="text-slate-600">Extract email addresses from websites with 98% accuracy</p>
          <div className="flex items-center justify-center gap-4">
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-green-500' : backendAvailable === false ? 'bg-red-500' : 'bg-yellow-500'}`} />
              <span className="text-slate-500">
                {wsConnected ? 'Connected' : backendAvailable === false ? 'Backend Offline' : 'Connecting...'}
              </span>
            </div>
            {userInfo && (
              <>
                <div className="text-slate-300">•</div>
                <button
                  onClick={handleEditProfile}
                  className="flex items-center gap-2 hover:bg-slate-100 px-2 py-1 rounded transition-colors"
                >
                  <User className="w-4 h-4 text-slate-400" />
                  <span className="text-slate-600">{userInfo.name}</span>
                </button>
              </>
            )}
          </div>
        </div>

        {/* Backend Status Warning */}
        {backendAvailable === false && (
          <Card className="border-yellow-200 bg-yellow-50">
            <CardContent className="pt-6">
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 w-10 h-10 rounded-full bg-yellow-100 flex items-center justify-center">
                  <XCircle className="w-5 h-5 text-yellow-600" />
                </div>
                <div className="flex-1">
                  <h3 className="text-yellow-900">Backend Not Available</h3>
                  <p className="text-yellow-700 mt-1">
                    The Python backend server is not running. Please start it by running:
                  </p>
                  <code className="block mt-2 p-3 bg-yellow-100 rounded text-yellow-900 font-mono">
                    python email_scraper_98.py
                  </code>
                  <p className="text-yellow-700 mt-2">
                    Make sure the backend is running on <strong>http://localhost:8000</strong>
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Main Input Card */}
        <Card>
          <CardHeader>
            <CardTitle>Start New Job</CardTitle>
            <CardDescription>Enter URLs to scrape (one per line)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              placeholder="https://example.com&#10;https://another-site.com&#10;domain.com"
              value={urls}
              onChange={(e) => setUrls(e.target.value)}
              rows={6}
              className="font-mono"
            />
            <div className="flex gap-2">
              <Button
                onClick={startScraping}
                disabled={!wsConnected || currentJob?.status === 'running' || backendAvailable === false}
                className="flex-1"
              >
                <PlayCircle className="w-4 h-4 mr-2" />
                {backendAvailable === false ? 'Backend Offline' : 'Start Scraping'}
              </Button>
              {currentJob?.status === 'running' && (
                <Button onClick={cancelJob} variant="destructive">
                  <StopCircle className="w-4 h-4 mr-2" />
                  Cancel
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Current Job Status */}
        {currentJob && (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    {getStatusIcon(currentJob.status)}
                    Current Job
                  </CardTitle>
                  <CardDescription>Job ID: {currentJob.id}</CardDescription>
                </div>
                <Badge variant={getStatusColor(currentJob.status)}>
                  {currentJob.status}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {currentJob.progress && (
                <div className="space-y-2">
                  <div className="flex justify-between text-slate-600">
                    <span>Progress: {currentJob.progress.done} / {currentJob.progress.total}</span>
                    <span>{totalEmails} emails found</span>
                  </div>
                  <Progress 
                    value={(currentJob.progress.done / currentJob.progress.total) * 100} 
                  />
                  {currentJob.progress.current && (
                    <p className="text-slate-500 truncate">
                      Currently scraping: {currentJob.progress.current}
                    </p>
                  )}
                </div>
              )}

              {currentJob.results && Object.keys(currentJob.results).length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-slate-900">Results</h3>
                    <Button
                      onClick={() => exportToCSV(currentJob.results!)}
                      variant="outline"
                      size="sm"
                    >
                      <Download className="w-4 h-4 mr-2" />
                      Export CSV
                    </Button>
                  </div>
                  <ScrollArea className="h-[300px] rounded-md border p-4">
                    <div className="space-y-4">
                      {Object.entries(currentJob.results).map(([url, emails]) => (
                        <div key={url} className="space-y-2">
                          <div className="flex items-start gap-2">
                            <Search className="w-4 h-4 mt-1 text-slate-400 flex-shrink-0" />
                            <div className="flex-1 min-w-0">
                              <p className="text-slate-900 truncate">{url}</p>
                              <p className="text-slate-500">{emails.length} email{emails.length !== 1 ? 's' : ''}</p>
                            </div>
                          </div>
                          {emails.length > 0 && (
                            <div className="ml-6 space-y-1">
                              {emails.map((email, idx) => (
                                <p key={idx} className="font-mono text-slate-700">
                                  {email}
                                </p>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Job History */}
        <Card>
          <CardHeader>
            <CardTitle>Job History</CardTitle>
            <CardDescription>Previous scraping jobs</CardDescription>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-[300px]">
              {jobs.length === 0 ? (
                <p className="text-center text-slate-500 py-8">No jobs yet</p>
              ) : (
                <div className="space-y-3">
                  {jobs.map((job) => (
                    <div
                      key={job.id}
                      className="flex items-center justify-between p-3 rounded-lg border hover:bg-slate-50 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        {getStatusIcon(job.status)}
                        <div>
                          <p className="text-slate-900">{job.id}</p>
                          <p className="text-slate-500">
                            {job.count} URLs • {new Date(job.created_at).toLocaleString()}
                          </p>
                        </div>
                      </div>
                      <Badge variant={getStatusColor(job.status)}>
                        {job.status}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
