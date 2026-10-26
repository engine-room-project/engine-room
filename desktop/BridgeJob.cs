using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
namespace EngineRoom {
 public sealed class DesktopJob {
  public volatile bool Complete;
  public string Output { get; private set; }
  public string Error { get; private set; }
  private Process child;
  private volatile bool cancelled;
  private readonly object gate=new object();
  public static string Quote(string value) {
   var text=new StringBuilder("\""); int slashes=0;
   foreach(char c in value) {
    if(c=='\\') {slashes++; continue;}
    text.Append('\\',c=='\"'?slashes*2+1:slashes); text.Append(c); slashes=0;
   }
   text.Append('\\',slashes*2); text.Append('\"'); return text.ToString();
  }
  public DesktopJob(string python,string root,string request,int timeoutMs) {
   if(Encoding.UTF8.GetByteCount(request)>262144 || timeoutMs<1 || timeoutMs>190000) throw new ArgumentException();
   var worker=new Thread(()=>Run(python,root,request,timeoutMs)); worker.IsBackground=true; worker.Start();
  }
  private byte[] Read(Stream stream,int limit) {
   using(var output=new MemoryStream()) {
    byte[] buffer=new byte[4096]; int count;
    while((count=stream.Read(buffer,0,buffer.Length))>0) {
     if(output.Length+count>limit) {Stop(); throw new IOException();}
     output.Write(buffer,0,count);
    }
    return output.ToArray();
   }
  }
  public void Stop() {
   cancelled=true;
   lock(gate) {if(child!=null) {try {if(!child.HasExited) child.Kill();} catch {}}}
  }
  private void Run(string python,string root,string request,int timeoutMs) {
   try {
    string code="import sys; sys.path.insert(0,sys.argv[1]); from engine_room.desktop_bridge import main; raise SystemExit(main())";
    var info=new ProcessStartInfo(python,"-I -c "+Quote(code)+" "+Quote(root));
    info.WorkingDirectory=root; info.UseShellExecute=false; info.CreateNoWindow=true;
    info.RedirectStandardInput=true; info.RedirectStandardOutput=true; info.RedirectStandardError=true;
    info.StandardOutputEncoding=new UTF8Encoding(false,true);
    using(var process=new Process()) {
     process.StartInfo=info;
     lock(gate) {if(cancelled) return; child=process; process.Start();}
     var stdout=Task.Run(()=>Read(process.StandardOutput.BaseStream,262144));
     var stderr=Task.Run(()=>Read(process.StandardError.BaseStream,16384));
     byte[] input=Encoding.UTF8.GetBytes(request); process.StandardInput.BaseStream.Write(input,0,input.Length); process.StandardInput.Close();
     if(!process.WaitForExit(timeoutMs)) {Stop(); throw new TimeoutException();}
     if(!Task.WaitAll(new Task[]{stdout,stderr},5000)) {Stop(); throw new TimeoutException();}
     if(cancelled) throw new OperationCanceledException();
     Output=new UTF8Encoding(false,true).GetString(stdout.Result);
     if(Output.Length==0) throw new IOException();
    }
   } catch {Error=cancelled?"The local request stopped. Check recovery before retrying.":"The local request did not finish. Check Python and controller access; shutdown is not confirmed.";}
   finally {if(cancelled && Error==null) Error="The local request stopped."; lock(gate) {child=null;} Complete=true;}
  }
 }
}

namespace EngineRoom {
 public sealed class SessionProcess {
  public volatile bool Complete;
  public string Error {get; private set;}
  private readonly object gate=new object();
  private readonly System.Collections.Generic.Queue<string> incoming=new System.Collections.Generic.Queue<string>();
  private readonly System.Collections.Generic.Queue<string> outgoing=new System.Collections.Generic.Queue<string>();
  private readonly AutoResetEvent changed=new AutoResetEvent(false);
  private Process child;
  private bool closing;
  public SessionProcess(string python,string root,string begin,int seconds) {
   if(seconds<1 || seconds>86700 || !Valid(begin)) throw new ArgumentException("Invalid session request");
   outgoing.Enqueue(begin);
   var thread=new Thread(()=>Run(python,root,seconds)); thread.IsBackground=true; thread.Start();
  }
  private static bool Valid(string value) {
   return value!=null && value.EndsWith("\n") && value.IndexOf('\n')==value.Length-1 && Encoding.UTF8.GetByteCount(value)<=262144;
  }
  private void Kill() {
   lock(gate) {try {if(child!=null && !child.HasExited) child.Kill();} catch {}}
  }
  private void Fail() {
   lock(gate) {if(Error==null) Error="The session helper could not continue. Preserve recovery records; shutdown is not confirmed.";}
   Kill(); changed.Set();
  }
  public string Take() {lock(gate) {return incoming.Count==0?null:incoming.Dequeue();}}
  public bool Command(string frame) {
   if(!Valid(frame)) throw new ArgumentException("Invalid session frame");
   bool overflow=false;
   lock(gate) {
    if(closing || Complete) return false;
    if(outgoing.Count>=8) overflow=true;
    else outgoing.Enqueue(frame);
   }
   if(overflow) {Fail(); return false;} changed.Set(); return true;
  }
  public void Pulse() {Command("{\"action\":\"pulse\"}\n");}
  public void Close() {
   lock(gate) {
    if(closing || Complete) return;
    closing=true; outgoing.Clear(); outgoing.Enqueue("{\"action\":\"stop\"}\n");
   }
   changed.Set();
   var grace=new Thread(()=>{Thread.Sleep(5000); if(!Complete) Kill();}); grace.IsBackground=true; grace.Start();
  }
  private void ReadOutput(Stream stream) {
   try {
    using(var frame=new MemoryStream()) {
     int value;
     while((value=stream.ReadByte())>=0) {
      if(frame.Length>=262144) throw new IOException();
      frame.WriteByte((byte)value);
      if(value==10) {
       string text=new UTF8Encoding(false,true).GetString(frame.ToArray()); frame.SetLength(0);
       lock(gate) {if(incoming.Count>=16) throw new IOException(); incoming.Enqueue(text);}
      }
     }
     if(frame.Length!=0) throw new IOException();
    }
   } catch {Fail();}
  }
  private void ReadError(Stream stream) {
   try {byte[] buffer=new byte[4096]; int count,total=0;
    while((count=stream.Read(buffer,0,buffer.Length))>0) {total+=count; if(total>16384) throw new IOException();}
   } catch {Fail();}
  }
  private void WriteInput(Stream stream) {
   try {
    while(true) {
     string frame=null; bool last=false;
     lock(gate) {if(outgoing.Count>0) frame=outgoing.Dequeue(); last=closing && outgoing.Count==0;}
     if(frame!=null) {byte[] data=Encoding.UTF8.GetBytes(frame); stream.Write(data,0,data.Length); stream.Flush();}
     if(last) {stream.Close(); return;}
     if(Complete) return;
     changed.WaitOne(1000);
    }
   } catch {if(!closing) Fail();}
  }
  private void Run(string python,string root,int seconds) {
   try {
    string code="import sys; sys.path.insert(0,sys.argv[1]); from engine_room.session_host import main; raise SystemExit(main())";
    var info=new ProcessStartInfo(python,"-I -c "+DesktopJob.Quote(code)+" "+DesktopJob.Quote(root));
    info.WorkingDirectory=root; info.UseShellExecute=false; info.CreateNoWindow=true;
    info.RedirectStandardInput=true; info.RedirectStandardOutput=true; info.RedirectStandardError=true;
    using(var process=new Process()) {
     process.StartInfo=info;
     lock(gate) {if(closing) return; child=process; process.Start();}
     var reader=new Thread(()=>ReadOutput(process.StandardOutput.BaseStream)); reader.IsBackground=true; reader.Start();
     var errors=new Thread(()=>ReadError(process.StandardError.BaseStream)); errors.IsBackground=true; errors.Start();
     var writer=new Thread(()=>WriteInput(process.StandardInput.BaseStream)); writer.IsBackground=true; writer.Start();
     if(!process.WaitForExit(seconds*1000)) {Fail(); process.WaitForExit(3000);}
     if(!reader.Join(3000) || !errors.Join(3000)) Fail();
    }
   } catch {Fail();}
   finally {lock(gate) {child=null; Complete=true;} changed.Set();}
  }
 }
}
