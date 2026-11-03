using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Collections.Generic;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("RTS AI - OpenBFME")]
[assembly: System.Reflection.AssemblyDescription("Local decision model game launcher")]
[assembly: System.Reflection.AssemblyVersion("1.0.0.0")]

static class GameLauncher {
    static string Quote(string value) { return "\"" + value + "\""; }
    static string Hash(string path) {
        using (var stream=File.OpenRead(path))
        using (var hash=SHA256.Create())
            return BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
    }
    static void RequireFile(string path) {
        if (!File.Exists(path)) throw new FileNotFoundException("Gerekli dosya bulunamadı: " + path);
    }
    [STAThread]
    static int Main(string[] args) {
        string root=AppDomain.CurrentDomain.BaseDirectory;
        string service=Path.Combine(root,@"AI-Yeni-Model\ai-service");
        bool check=args.Length==1 && args[0]=="--check";
        try {
            string python=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),@".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe");
            string host=Path.Combine(service,"host.py"), configPath=Path.Combine(service,"runtime.json");
            RequireFile(python); RequireFile(host); RequireFile(configPath);
            var json=new JavaScriptSerializer();
            var config=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(configPath,Encoding.UTF8));
            if (!config.ContainsKey("strict_model_only") || !(bool)config["strict_model_only"])
                throw new InvalidOperationException("Oyun paketi model karar yetkisi kipinde değil.");
            foreach (string key in new [] {"game_executable","weights","spend_weights","reward_config"}) RequireFile((string)config[key]);
            foreach (var pair in new [] {new [] {"weights","sha256"},new [] {"spend_weights","spend_sha256"},new [] {"reward_config","reward_sha256"}})
                if (Hash((string)config[pair[0]])!=(string)config[pair[1]])
                    throw new InvalidOperationException("Dosya doğrulaması başarısız: " + pair[0]);
            string gameFolder=Path.GetDirectoryName((string)config["game_executable"]);
            RequireFile(Path.Combine(gameFolder,"OpenBFME.pck"));
            RequireFile(Path.Combine(gameFolder,"openbfme.windows.template_debug.x86_64.dll"));
            string arguments=Quote(host)+" --config "+Quote(configPath);
            if (check) {
                File.WriteAllText(Path.Combine(service,"game-launcher-check.json"),json.Serialize(new {
                    ok=true, strict_model_only=true, python=python, host=host, arguments=arguments,
                    game_executable=config["game_executable"], weights_sha256=config["sha256"],
                    spend_sha256=config["spend_sha256"], launches_training=false, uses_model=false
                }),new UTF8Encoding(false));
                return 0;
            }
            string name;
            using (var sha=SHA256.Create()) name=BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(root.ToLowerInvariant()))).Replace("-", "");
            bool first;
            using (var mutex=new Mutex(true,@"Local\RTSAIPlay-"+name,out first)) {
                if (!first) { MessageBox.Show("AI oyunu zaten açık.","RTS AI",MessageBoxButtons.OK,MessageBoxIcon.Information); return 2; }
                string logs=Path.Combine(service,"logs"); Directory.CreateDirectory(logs);
                string logPath=Path.Combine(logs,"game-launcher-"+DateTime.Now.ToString("yyyyMMdd-HHmmss")+".log");
                using (var log=new StreamWriter(logPath,false,new UTF8Encoding(false)))
                using (var process=new Process()) {
                    log.AutoFlush=true;
                    process.StartInfo=new ProcessStartInfo(python,arguments) {
                        WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,
                        RedirectStandardOutput=true,RedirectStandardError=true
                    };
                    process.StartInfo.EnvironmentVariables["PYTHONUTF8"]="1";
                    process.OutputDataReceived+=(sender,e)=>{ if (e.Data!=null) lock(log) log.WriteLine(e.Data); };
                    process.ErrorDataReceived+=(sender,e)=>{ if (e.Data!=null) lock(log) log.WriteLine(e.Data); };
                    process.Start(); process.BeginOutputReadLine(); process.BeginErrorReadLine();
                    process.WaitForExit();
                    // The model host reports its own game/startup errors in a dialog.
                    return process.ExitCode;
                }
            }
        } catch (Exception error) {
            if (check) {
                Directory.CreateDirectory(service);
                File.WriteAllText(Path.Combine(service,"game-launcher-check.json"),new JavaScriptSerializer().Serialize(new {ok=false,error=error.Message}),new UTF8Encoding(false));
            } else MessageBox.Show(error.Message,"RTS AI - Başlatma hatası",MessageBoxButtons.OK,MessageBoxIcon.Error);
            return 1;
        }
    }
}
