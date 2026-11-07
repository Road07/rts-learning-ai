using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Windows.Forms;

sealed class EconomyWindow : Form {
    readonly string root=AppDomain.CurrentDomain.BaseDirectory;
    readonly Button train=new Button(), random=new Button(), stop=new Button(), folder=new Button();
    readonly NumericUpDown steps=new NumericUpDown(), workers=new NumericUpDown();
    readonly Label status=new Label(), destination=new Label();
    readonly TextBox log=new TextBox();
    readonly bool verify;
    PrivateJob job;
    Process process;
    StreamWriter writer;
    string output, gate;
    bool stopping;
    public EconomyWindow(bool check) {
        verify=check; Text="OpenBFME • Ekonomi Deneyi"; ClientSize=new Size(880,600);
        MinimumSize=new Size(820,580); StartPosition=FormStartPosition.CenterScreen;
        Font=new Font("Segoe UI",10); BackColor=Color.FromArgb(242,246,250);
        var grid=new TableLayoutPanel {Dock=DockStyle.Fill,Padding=new Padding(24),ColumnCount=1,RowCount=7};
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
        foreach(int h in new int[]{48,66,48,48,48}) grid.RowStyles.Add(new RowStyle(SizeType.Absolute,h));
        grid.RowStyles.Add(new RowStyle(SizeType.Percent,100)); grid.RowStyles.Add(new RowStyle(SizeType.Absolute,55)); Controls.Add(grid);
        grid.Controls.Add(new Label {Text="AI / Ekonomi Deneyi",Font=new Font("Segoe UI",22,FontStyle.Bold),ForeColor=Color.FromArgb(25,45,69),Dock=DockStyle.Fill},0,0);
        grid.Controls.Add(new Label {Text="180 oyun saniyelik ekonomi görevi • Başsız çalışma\nAyrı MaskablePPO deneyi. Sonuçlar mevcut oyun modeline otomatik aktarılmaz.",Dock=DockStyle.Fill},0,1);
        var settings=new FlowLayoutPanel {Dock=DockStyle.Fill};
        settings.Controls.Add(new Label {Text="Eğitim adımı",AutoSize=true,Margin=new Padding(0,7,8,0)});
        steps.Minimum=100; steps.Maximum=10000000; steps.Increment=1000; steps.Value=200000; steps.Width=125; steps.ThousandsSeparator=true; settings.Controls.Add(steps);
        settings.Controls.Add(new Label {Text="Paralel maç",AutoSize=true,Margin=new Padding(24,7,8,0)});
        workers.Minimum=1; workers.Maximum=32; workers.Value=8; workers.Width=65; settings.Controls.Add(workers); grid.Controls.Add(settings,0,2);
        status.Text="Hazır. Eğitim uzun sürebilir (varsayılan yaklaşık 10–16 saat)."; status.Dock=DockStyle.Fill; status.ForeColor=Color.FromArgb(22,82,145); grid.Controls.Add(status,0,3);
        destination.Text="Her çalıştırmada ayrı bir sonuç klasörü oluşturulur."; destination.Dock=DockStyle.Fill; destination.AutoEllipsis=true; grid.Controls.Add(destination,0,4);
        log.Multiline=true; log.ReadOnly=true; log.ScrollBars=ScrollBars.Both; log.WordWrap=false; log.Dock=DockStyle.Fill; log.BackColor=Color.White; grid.Controls.Add(log,0,5);
        var buttons=new FlowLayoutPanel {Dock=DockStyle.Fill,Padding=new Padding(0,10,0,0)};
        train.Text="Eğitimi başlat"; random.Text="Rastgele ajanı ölç"; stop.Text="Durdur"; folder.Text="Sonuçları aç";
        foreach(var b in new[]{train,random,stop,folder}) {b.AutoSize=true; b.Height=34; buttons.Controls.Add(b);} grid.Controls.Add(buttons,0,6);
        stop.Enabled=false; folder.Enabled=false;
        train.Click+=(s,e)=>StartRun("train"); random.Click+=(s,e)=>StartRun("random"); stop.Click+=(s,e)=>StopRun();
        folder.Click+=(s,e)=>{if(output!=null && Directory.Exists(output)) Process.Start("explorer.exe",Quote(output));};
        FormClosing+=(s,e)=>{stopping=true; if(job!=null)job.Dispose();};
        Shown+=(s,e)=>{if(verify) {
            string dir=Path.Combine(root,@"AI-Test-Sahasi\economy-launcher-check"); Directory.CreateDirectory(dir);
            using(var bitmap=new Bitmap(Width,Height)) {DrawToBitmap(bitmap,new Rectangle(0,0,Width,Height));bitmap.Save(Path.Combine(dir,"launcher.png"));}
            StartRun("check");
        }};
        if(verify) {ShowInTaskbar=false;Opacity=0;}
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
    void Append(string line) {
        if(line==null || IsDisposed)return;
        if(InvokeRequired) {try {BeginInvoke(new Action<string>(Append),line);} catch(InvalidOperationException){} return;}
        log.AppendText(line+Environment.NewLine); if(writer!=null){writer.WriteLine(line);writer.Flush();}
    }
    void StartRun(string mode) {
        if(process!=null)return;
        try {
            string python=Path.Combine(root,@"AI-PyTorch\venv\Scripts\python.exe");
            string script=Path.Combine(root,@"ai-mod-source\tools\local_strategy\training\economy_launcher_worker.py");
            if(!File.Exists(python)||!File.Exists(script))throw new FileNotFoundException("Eğitim ortamı bulunamadı. EXE'yi proje klasöründen çalıştır.");
            string parent=Path.Combine(root,verify?@"AI-Test-Sahasi\economy-launcher-check":@"AI-Egitim\ekonomi-deneyleri"); Directory.CreateDirectory(parent);
            string id=mode+"-"+DateTime.Now.ToString("yyyyMMdd-HHmmss")+"-"+Guid.NewGuid().ToString("N").Substring(0,6);
            output=Path.Combine(parent,id); gate=Path.Combine(parent,id+".gate");
            writer=new StreamWriter(Path.Combine(parent,id+".log"),false,Encoding.UTF8);
            stopping=false; log.Clear(); destination.Text="Sonuç: "+output;
            var info=new ProcessStartInfo(python,"-u "+Quote(script)+" --gate "+Quote(gate)+" --mode "+mode+" --output "+Quote(output)+" --parallel "+workers.Value+" --timesteps "+steps.Value);
            info.WorkingDirectory=root;info.UseShellExecute=false;info.CreateNoWindow=true;info.RedirectStandardOutput=true;info.RedirectStandardError=true;
            info.StandardOutputEncoding=Encoding.UTF8;info.StandardErrorEncoding=Encoding.UTF8;info.EnvironmentVariables["PYTHONUTF8"]="1";info.EnvironmentVariables["PYTHONUNBUFFERED"]="1";
            job=new PrivateJob(); process=new Process {StartInfo=info,EnableRaisingEvents=true};
            process.OutputDataReceived+=(s,e)=>Append(e.Data);process.ErrorDataReceived+=(s,e)=>Append(e.Data);
            process.Exited+=(s,e)=>{try{BeginInvoke(new Action(Finished));}catch(InvalidOperationException){}};
            process.Start(); job.Assign(process); process.BeginOutputReadLine();process.BeginErrorReadLine();File.WriteAllText(gate,"ready");
            train.Enabled=random.Enabled=steps.Enabled=workers.Enabled=false; stop.Enabled=true;folder.Enabled=true;
            status.Text=mode=="random"?"Rastgele ajan: aynı 5 sabit maç ölçülüyor…":"Eğitim hazırlanıyor / çalışıyor…";
        }catch(Exception ex) {Append(ex.Message);if(process!=null) {try{if(!process.HasExited)process.Kill();}catch{}} Cleanup();status.Text="Başlatılamadı: "+ex.Message;if(verify){Environment.ExitCode=1;Close();}}
    }
    void StopRun() {if(job==null)return;stopping=true;status.Text="Durduruluyor…";job.Dispose();}
    void Finished() {
        if(process==null)return;process.WaitForExit();int code=process.ExitCode;
        status.Text=stopping?"Durduruldu. Önceden kaydedilmiş çıktılar klasörde tutuldu.":code==0?"Tamamlandı. Sonuçlar klasörde hazır.":"İşlem hata ile bitti. Ayrıntılar aşağıda ve günlük dosyasında.";
        if(verify)File.WriteAllText(Path.Combine(root,@"AI-Test-Sahasi\economy-launcher-check\verification.json"),"{\"exit_code\":"+code+",\"training_started\":false,\"job_gate_verified\":"+(code==0?"true":"false")+"}");
        Cleanup();if(verify){Environment.ExitCode=code;Close();}
    }
    void Cleanup() {
        if(job!=null){job.Dispose();job=null;}if(process!=null){process.Dispose();process=null;}
        if(writer!=null){writer.Dispose();writer=null;}if(gate!=null&&File.Exists(gate))File.Delete(gate);
        train.Enabled=random.Enabled=steps.Enabled=workers.Enabled=true;stop.Enabled=false;
    }
    [STAThread] static void Main(string[] args) {Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new EconomyWindow(Array.IndexOf(args,"--verify")>=0));}
}
