using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

sealed class PrivateJob : IDisposable {
    [StructLayout(LayoutKind.Sequential)] struct Basic {
        public long ProcessTime, JobTime;
        public uint Flags;
        public UIntPtr MinWorkingSet, MaxWorkingSet;
        public uint ActiveProcesses;
        public UIntPtr Affinity;
        public uint Priority, Scheduling;
    }
    [StructLayout(LayoutKind.Sequential)] struct Io { public ulong Read, Write, Other, ReadBytes, WriteBytes, OtherBytes; }
    [StructLayout(LayoutKind.Sequential)] struct Limits {
        public Basic Basic; public Io Io;
        public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job, int infoClass, ref Limits limits, uint length);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    IntPtr handle;
    public PrivateJob() {
        handle=CreateJobObject(IntPtr.Zero,null);
        if (handle==IntPtr.Zero) throw new Win32Exception();
        Limits limits=new Limits(); limits.Basic.Flags=0x2000; // KILL_ON_JOB_CLOSE
        if (!SetInformationJobObject(handle,9,ref limits,(uint)Marshal.SizeOf(typeof(Limits)))) { Dispose(); throw new Win32Exception(); }
    }
    public void Assign(Process process) { if (!AssignProcessToJobObject(handle,process.Handle)) throw new Win32Exception(); }
    public void Dispose() { if (handle!=IntPtr.Zero) { CloseHandle(handle); handle=IntPtr.Zero; } }
}

sealed class TrainingWindow : Form {
    readonly string root, python, script, statePath, checkDir;
    readonly bool verify, renderOnly;
    readonly Label status=new Label(), details=new Label();
    readonly TextBox log=new TextBox();
    readonly Button start=new Button(), stop=new Button(), records=new Button();
    readonly ComboBox duration=new ComboBox();
    readonly int[] minuteOptions=new int[]{3,5,15,30};
    readonly JavaScriptSerializer json=new JavaScriptSerializer();
    PrivateJob job;
    Process process;
    string gate;
    bool running, requestedStop, closeAfterStop, jobAssigned;
    int completed;
    double? lastReward;

    public TrainingWindow(bool verification, bool renderingOnly) {
        verify=verification;
        renderOnly=renderingOnly;
        root=AppDomain.CurrentDomain.BaseDirectory;
        python=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),@".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe");
        script=Path.Combine(root,@"ai-mod-source\tools\local_strategy\training\training_supervisor.py");
        checkDir=Path.Combine(root,@"AI-Test-Sahasi\launcher-check");
        statePath=verify ? Path.Combine(checkDir,"state-"+Guid.NewGuid().ToString("N")+".json") : Path.Combine(root,@"AI-Egitim\otomatik-dongu\launcher-state.json");
        Text="OpenBFME • Otomatik Eğitim";
        ClientSize=new Size(820,560); MinimumSize=new Size(740,540);
        StartPosition=FormStartPosition.CenterScreen;
        BackColor=Color.FromArgb(243,246,251);
        Font=new Font("Segoe UI",10);
        AutoScaleMode=AutoScaleMode.Dpi;
        var grid=new TableLayoutPanel { Dock=DockStyle.Fill, Padding=new Padding(24), ColumnCount=1, RowCount=7 };
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
        foreach (int height in new int[]{44,44,68,28}) grid.RowStyles.Add(new RowStyle(SizeType.Absolute,height));
        grid.RowStyles.Add(new RowStyle(SizeType.Percent,100));
        grid.RowStyles.Add(new RowStyle(SizeType.Absolute,52));
        grid.RowStyles.Add(new RowStyle(SizeType.Absolute,28));
        Controls.Add(grid);
        var title=new Label { Text="OpenBFME  /  AI Eğitimi", Dock=DockStyle.Fill, Font=new Font("Segoe UI",20,FontStyle.Bold), ForeColor=Color.FromArgb(25,45,69) };
        grid.Controls.Add(title,0,0);
        grid.Controls.Add(new Label { Text="Aday model kısa oyun senaryolarında deneyerek öğrenir.\nTamamlanan eğitim kaydedilir; sonraki açılışta devam eder.", Dock=DockStyle.Fill, ForeColor=Color.FromArgb(70,83,104) },0,1);
        status.Dock=DockStyle.Fill; status.Font=new Font("Segoe UI",12,FontStyle.Bold);
        status.Text="Tur süresini seçip Başlat'a bas."; status.ForeColor=Color.FromArgb(22,82,145);
        grid.Controls.Add(status,0,2);
        details.Dock=DockStyle.Fill; details.Text="Tamamlanan tur: 0";
        grid.Controls.Add(details,0,3);
        log.Dock=DockStyle.Fill; log.Multiline=true; log.ReadOnly=true; log.ScrollBars=ScrollBars.Vertical;
        log.BackColor=Color.White; log.ForeColor=Color.FromArgb(40,55,75); log.BorderStyle=BorderStyle.FixedSingle;
        grid.Controls.Add(log,0,4);
        var buttons=new FlowLayoutPanel { Dock=DockStyle.Fill, Margin=Padding.Empty, Padding=new Padding(0,10,0,0), WrapContents=false };
        buttons.Controls.Add(new Label {Text="Tur süresi:",AutoSize=true,Margin=new Padding(0,7,4,0)});
        duration.DropDownStyle=ComboBoxStyle.DropDownList; duration.Width=100;
        foreach (int minutes in minuteOptions) duration.Items.Add(minutes+" dakika");
        duration.SelectedIndex=0;
        try {
            string settings=Path.Combine(Path.GetDirectoryName(statePath),"launcher-settings.json");
            if (File.Exists(settings)) {
                var saved=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(settings,Encoding.UTF8));
                int index=Array.IndexOf(minuteOptions,Convert.ToInt32(saved["minutes"]));
                if (index>=0) duration.SelectedIndex=index;
            }
        } catch { }
        buttons.Controls.Add(duration);
        start.Text="Başlat"; stop.Text="Durdur"; records.Text="Kayıtları aç";
        stop.Enabled=false;
        foreach (Button b in new Button[]{start,stop,records}) { b.Size=new Size(140,34); b.FlatStyle=FlatStyle.Flat; b.BackColor=Color.White; buttons.Controls.Add(b); }
        start.Click+=delegate { BeginTraining(); }; stop.Click+=delegate { StopTraining(); };
        records.Click+=delegate { string folder=Path.GetDirectoryName(statePath); Directory.CreateDirectory(folder); Process.Start(new ProcessStartInfo(folder){UseShellExecute=true}); };
        grid.Controls.Add(buttons,0,5);
        grid.Controls.Add(new Label { Text="Tamamlanan eğitim sonraki oyun açılışında otomatik kullanılır.", Dock=DockStyle.Fill, Font=new Font("Segoe UI",9), ForeColor=Color.FromArgb(85,96,113) },0,6);
        FormClosing+=OnClosing;
        Shown+=delegate { if (verify) SaveImage("initial.png"); if (renderOnly) { SaveImage("launcher.png"); Close(); return; } if (verify) BeginTraining(); };
        if (verify) { Opacity=0; ShowInTaskbar=false; }
    }

    static string Quote(string value) {
        StringBuilder b=new StringBuilder("\""); int slashes=0;
        foreach (char c in value) {
            if (c=='\\') { slashes++; continue; }
            if (c=='"') b.Append('\\',slashes*2+1);
            else b.Append('\\',slashes);
            b.Append(c); slashes=0;
        }
        b.Append('\\',slashes*2); b.Append('"'); return b.ToString();
    }
    void Ui(Action action) { if (IsDisposed || !IsHandleCreated) return; try { BeginInvoke(action); } catch (InvalidOperationException) {} }
    void AddLog(string text) { log.AppendText(DateTime.Now.ToString("HH:mm:ss")+"  "+text+Environment.NewLine); }
    void BeginTraining() {
        if (running) return;
        try {
            if (!File.Exists(python) || !File.Exists(script) || !File.Exists(Path.Combine(root,@"AI-Yeni-Model\ai-service\runtime.json"))) throw new FileNotFoundException("Python veya eğitim paketi bulunamadı. Bu exe oyun klasöründe kalmalı.");
            Directory.CreateDirectory(Path.GetDirectoryName(statePath));
            int minutes=minuteOptions[duration.SelectedIndex];
            if (!verify) File.WriteAllText(Path.Combine(Path.GetDirectoryName(statePath),"launcher-settings.json"),json.Serialize(new {minutes=minutes}),Encoding.UTF8);
            gate=Path.Combine(Path.GetDirectoryName(statePath),"gate-"+Guid.NewGuid().ToString("N")+".flag");
            job=new PrivateJob();
            var info=new ProcessStartInfo(python,Quote(script)+" --state "+Quote(statePath)+" --gate "+Quote(gate)+" --minutes "+minutes+(verify ? " --smoke" : ""));
            info.WorkingDirectory=root; info.UseShellExecute=false; info.CreateNoWindow=true;
            info.RedirectStandardOutput=true; info.RedirectStandardError=true;
            info.StandardOutputEncoding=Encoding.UTF8; info.StandardErrorEncoding=Encoding.UTF8;
            info.EnvironmentVariables["PYTHONUTF8"]="1"; info.EnvironmentVariables["PYTHONIOENCODING"]="utf-8";
            info.EnvironmentVariables["PYTHONUNBUFFERED"]="1";
            process=new Process(); process.StartInfo=info;
            process.OutputDataReceived+=delegate(object sender,DataReceivedEventArgs e) { if (e.Data!=null) Ui(delegate { HandleLine(e.Data); }); };
            process.ErrorDataReceived+=delegate(object sender,DataReceivedEventArgs e) { if (e.Data!=null) Ui(delegate { AddLog(e.Data); }); };
            process.Start();
            try { job.Assign(process); jobAssigned=true; } catch { process.Kill(); throw; }
            running=true; requestedStop=false; start.Enabled=false; stop.Enabled=true; duration.Enabled=false;
            process.BeginOutputReadLine(); process.BeginErrorReadLine();
            File.WriteAllText(gate,"owned",Encoding.ASCII);
            status.Text="Eğitim başlatılıyor…";
            AddLog(verify ? "Kısa kontrol: yalnız bir adet 6 saniyelik tur." : "Sürekli eğitim başlatıldı. Durdur düğmesiyle bitirebilirsin.");
            Process current=process;
            Task.Factory.StartNew(delegate { current.WaitForExit(); int code=current.ExitCode; Ui(delegate { Finished(code); }); });
        } catch (Exception error) {
            if (job!=null) { job.Dispose(); job=null; }
            running=false; start.Enabled=true; stop.Enabled=false; duration.Enabled=true;
            status.Text="Eğitim başlatılamadı"; AddLog(error.Message);
            if (verify) FinishVerification(false,error.Message);
        }
    }
    void HandleLine(string line) {
        try {
            var row=json.Deserialize<Dictionary<string,object>>(line);
            string kind=Convert.ToString(row["event"]);
            if (row.ContainsKey("completed")) completed=Convert.ToInt32(row["completed"]);
            if (row.ContainsKey("last_reward") && row["last_reward"]!=null) lastReward=Convert.ToDouble(row["last_reward"]);
            if (kind=="ready") AddLog(Convert.ToBoolean(row["resume"]) ? "Tamamlanmış son modelden devam ediliyor." : "İlk eğitim kaydı oluşturuluyor.");
            if (kind=="running") {
                string stage=Convert.ToString(row["stage"]), scenario=Convert.ToString(row["case"]);
                string name=stage=="opening" ? "Başlangıç" : stage=="late" ? "Geç oyun" : "Orta oyun";
                status.Text="Tur "+row["round"]+"  •  "+name+"\n"+(Convert.ToBoolean(row["evaluation"]) ? "Eğitim ve karşılaştırma kontrolü" : "Model karar veriyor ve sonuçları ölçülüyor");
                AddLog("Tur "+row["round"]+": "+name+" / "+scenario+" ("+row["seconds"]+" sn).");
            }
            if (kind=="completed") {
                double reward=Convert.ToDouble(row["reward"]);
                lastReward=reward;
                UpdateDetails();
                AddLog("Tur tamamlandı. "+(verify ? "Kontrol modeli ayrı kaydedildi" : "Model oyuna aktarıldı")+"; ödül "+reward.ToString("+0.000;-0.000;0.000")+".");
                return;
            }
            if (kind=="episode_phase") {
                string phase=Convert.ToString(row["phase"]);
                string message=phase.StartsWith("eval-baseline") ? "Karşılaştırma 1/2 • önceki model" : phase.StartsWith("eval-candidate") ? "Karşılaştırma 2/2 • yeni model" : "Eğitim • deneyim toplanıyor";
                status.Text=message+"\nBu aşama bitince kayıt alınacak.";
                AddLog(message+". Seçilen süre her aşama için ayrı uygulanır.");
            }
            if (kind=="error") { status.Text="Eğitim durdu • hata kaydedildi"; AddLog(Convert.ToString(row["message"])); }
            UpdateDetails();
        } catch { AddLog(line); }
    }
    void UpdateDetails() { details.Text="Tamamlanan tur: "+completed+(lastReward.HasValue ? "   •   Son ödül: "+lastReward.Value.ToString("+0.000;-0.000;0.000") : ""); }
    void StopTraining() {
        if (!running) return;
        requestedStop=true; status.Text="Eğitim durduruluyor…";
        AddLog("Bu aşama kesiliyor. Tamamlanmış eğitimden sonraki karşılaştırma yeniden açılışta devam eder.");
        if (job!=null) { job.Dispose(); job=null; }
    }
    void Finished(int code) {
        running=false; start.Enabled=true; stop.Enabled=false; duration.Enabled=true;
        if (job!=null) { job.Dispose(); job=null; }
        if (gate!=null && File.Exists(gate)) File.Delete(gate);
        if (requestedStop) status.Text="Durduruldu • tamamlanan turlar korundu";
        else if (code==0) status.Text=verify ? "Kısa kontrol tamamlandı" : "Eğitim tamamlandı";
        else status.Text="Eğitim hata nedeniyle durdu • kayıtları incele";
        if (verify) { FinishVerification(code==0 && completed==1 && jobAssigned,null); return; }
        if (closeAfterStop) Close();
    }
    void OnClosing(object sender,FormClosingEventArgs e) {
        if (running) { closeAfterStop=true; e.Cancel=true; StopTraining(); }
    }
    void SaveImage(string name) {
        Directory.CreateDirectory(checkDir);
        using (Bitmap bitmap=new Bitmap(Width,Height)) { DrawToBitmap(bitmap,new Rectangle(0,0,Width,Height)); bitmap.Save(Path.Combine(checkDir,name)); }
    }
    void FinishVerification(bool ok,string error) {
        SaveImage("launcher.png");
        bool killed=false;
        if (ok) {
            var info=new ProcessStartInfo(python,"-c "+Quote("import time; time.sleep(60)")) { UseShellExecute=false, CreateNoWindow=true };
            using (Process probe=Process.Start(info)) { using (var owned=new PrivateJob()) owned.Assign(probe); killed=probe.WaitForExit(3000); if (!killed) probe.Kill(); }
        }
        var result=new Dictionary<string,object> { {"ok",ok && killed},{"completed",completed},{"job_assigned",jobAssigned},{"stop_job_verified",killed},{"error",error},{"state",statePath} };
        File.WriteAllText(Path.Combine(checkDir,"ui-check.json"),json.Serialize(result),new UTF8Encoding(false));
        Environment.ExitCode=ok && killed ? 0 : 1;
        Close();
    }
}

static class Program {
    [STAThread] static void Main(string[] args) {
        bool renderOnly=Array.IndexOf(args,"--render-only")>=0;
        bool verify=Array.IndexOf(args,"--verify")>=0 || renderOnly;
        string identity;
        using (var hash=SHA256.Create()) identity=BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(AppDomain.CurrentDomain.BaseDirectory.ToUpperInvariant()))).Replace("-","");
        bool created;
        using (var mutex=new Mutex(true,@"Local\OpenBFMETraining-"+identity,out created)) {
            if (!created) { if (!verify) MessageBox.Show("Eğitim penceresi zaten açık.","OpenBFME"); Environment.ExitCode=2; return; }
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new TrainingWindow(verify,renderOnly));
        }
    }
}
