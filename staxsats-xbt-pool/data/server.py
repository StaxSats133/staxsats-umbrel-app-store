from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import urllib.request

GATEWAY = "http://host.docker.internal:7153/stats.json"
PRIME = "http://172.17.0.1:28916/stats.json"

HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>XBT Pool</title>

<style>
*{box-sizing:border-box}

body{
    margin:0;
    background:
      radial-gradient(circle at 50% -20%,rgba(168,85,247,.16),transparent 38%),
      linear-gradient(180deg,#070910,#0b0e15 55%,#07090e);
    color:#f7f7fb;
    font-family:Arial,Helvetica,sans-serif;
}

.wrap{
    max-width:1500px;
    margin:auto;
    padding:28px;
}

header{
    display:flex;
    align-items:flex-end;
    justify-content:space-between;
    gap:20px;
    margin-bottom:28px;
}

h1{
    margin:0;
    font-size:42px;
    letter-spacing:.5px;
    color:#b45cff;
}

.subtitle{
    margin-top:5px;
    color:#8793a8;
    font-size:16px;
}

.live{
    color:#4ade80;
    font-size:14px;
    white-space:nowrap;
}

.section{
    margin:28px 0 12px;
    font-weight:bold;
    font-size:14px;
    letter-spacing:.11em;
    color:#ccd5e2;
}

.grid{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(210px,1fr));
    gap:16px;
}

.card{
    background:rgba(20,24,34,.94);
    border:1px solid rgba(168,85,247,.38);
    border-radius:17px;
    padding:20px;
    min-height:118px;
    box-shadow:
      0 12px 35px rgba(0,0,0,.14),
      inset 0 1px rgba(255,255,255,.015);
}

.label{
    color:#9ca9bb;
    font-size:13px;
    text-transform:uppercase;
    letter-spacing:.08em;
}

.value{
    margin-top:10px;
    font-size:30px;
    line-height:1.08;
    font-weight:750;
}

.small{
    font-size:21px;
}

.tiny{
    font-size:15px;
    word-break:break-all;
    line-height:1.45;
}

.ok{color:#4ade80}
.bad{color:#fb7185}
.cyan{color:#5ee7f4}
.purple{color:#c26cff}
.gold{color:#ffd21f}

.wide{
    grid-column:1/-1;
}

.graph-card{
    background:rgba(20,24,34,.94);
    border:1px solid rgba(168,85,247,.38);
    border-radius:17px;
    padding:20px;
}

.graph-head{
    display:flex;
    justify-content:space-between;
    align-items:center;
    margin-bottom:16px;
}

.graph-title{
    font-weight:bold;
    color:#d9e0eb;
}

.graph-now{
    color:#5ee7f4;
    font-size:21px;
    font-weight:bold;
}

svg{
    width:100%;
    height:220px;
    display:block;
    overflow:visible;
}

.graph-line{
    fill:none;
    stroke:#b45cff;
    stroke-width:3;
    vector-effect:non-scaling-stroke;
}

.graph-fill{
    fill:url(#fade);
}

.graph-grid{
    stroke:rgba(255,255,255,.07);
    stroke-width:1;
}

.banner{
    display:none;
    padding:18px 20px;
    margin-bottom:22px;
    border-radius:16px;
    border:1px solid #ffd21f;
    background:rgba(250,204,21,.09);
    color:#ffd21f;
    font-weight:bold;
    font-size:20px;
}

.footer{
    margin-top:30px;
    padding-bottom:20px;
    color:#6f7989;
    font-size:12px;
}

@media(max-width:700px){
    .wrap{padding:17px}
    h1{font-size:32px}
    header{align-items:flex-start;flex-direction:column}
    .value{font-size:25px}
}
</style>
</head>

<body>
<div class="wrap">

<header>
    <div>
        <h1>XBT Pool</h1>
        <div class="subtitle">RATUM Prime + Gateway • BLAKE2b</div>
    </div>
    <div class="live" id="live">CONNECTING...</div>
</header>

<div id="blockBanner" class="banner"></div>

<div class="section">MINING</div>
<div class="grid" id="mining"></div>

<div class="section">HASHRATE HISTORY</div>
<div class="graph-card">
    <div class="graph-head">
        <div class="graph-title">Rolling Gateway Hashrate</div>
        <div class="graph-now" id="graphNow">0 TH/s</div>
    </div>

    <svg viewBox="0 0 1000 220" preserveAspectRatio="none">
        <defs>
            <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#b45cff" stop-opacity=".35"/>
                <stop offset="100%" stop-color="#b45cff" stop-opacity="0"/>
            </linearGradient>
        </defs>

        <line class="graph-grid" x1="0" y1="55" x2="1000" y2="55"/>
        <line class="graph-grid" x1="0" y1="110" x2="1000" y2="110"/>
        <line class="graph-grid" x1="0" y1="165" x2="1000" y2="165"/>

        <path id="graphFill" class="graph-fill"></path>
        <path id="graphLine" class="graph-line"></path>
    </svg>
</div>

<div class="section">YOUR MINER</div>
<div class="grid" id="miner"></div>

<div class="section">XBT NETWORK</div>
<div class="grid" id="network"></div>

<div class="section">PAYOUT WINDOW</div>
<div class="grid" id="window"></div>

<div class="footer">
Estimated payout is what your current payout-window share would receive if the pool found a block now. It is not an earned balance until a block is actually found and settled.
</div>

</div>

<script>
function num(v,d=2){
    if(v===null || v===undefined || isNaN(Number(v))) return "N/A";
    return Number(v).toLocaleString(undefined,{
        maximumFractionDigits:d
    });
}

function card(label,value,cls=""){
    return `
    <div class="card">
        <div class="label">${label}</div>
        <div class="value ${cls}">${value}</div>
    </div>`;
}

function drawGraph(values){
    const line=document.getElementById("graphLine");
    const fill=document.getElementById("graphFill");

    if(!values || values.length < 2){
        line.setAttribute("d","");
        fill.setAttribute("d","");
        return;
    }

    let max=Math.max(...values,0.001);

    let points=values.map((v,i)=>{
        let x=(i/(values.length-1))*1000;
        let y=210-(v/max)*190;
        return [x,y];
    });

    let path="M "+points.map(p=>p.join(" ")).join(" L ");
    line.setAttribute("d",path);

    let fillPath=path+
        " L 1000 220 L 0 220 Z";

    fill.setAttribute("d",fillPath);
}

async function refresh(){
    try{
        const r=await fetch("/api/stats?ts="+Date.now(),{
            cache:"no-store"
        });

        if(!r.ok) throw new Error("HTTP "+r.status);

        const d=await r.json();

        document.getElementById("live").textContent =
            "LIVE • "+new Date().toLocaleTimeString();

        document.getElementById("mining").innerHTML =
            card(
                "Status",
                d.status,
                d.status.includes("Ready") ? "ok":"bad"
            ) +
            card("Connected Miners",d.connections) +
            card("Live Hashrate",num(d.hashrate,3)+" TH/s","cyan") +
            card("Accepted Shares",num(d.accepted,0)) +
            card(
                "Rejected Shares",
                num(d.rejected,0),
                d.rejected>0 ? "bad":""
            ) +
            card("Share Difficulty",num(d.shareDifficulty,0)) +
            card("Gateway Uptime",d.uptime,"small");

        document.getElementById("miner").innerHTML =
            card("Payout Identity",d.identity || "N/A","tiny") +
            card("Prime Hashrate",num(d.primeHashrate,3)+" TH/s","cyan") +
            card("Window Work",d.minerWork || "0") +
            card("Window Share",num(d.sharePercent,2)+"%","purple") +
            card(
                "Payable",
                d.payable ? "YES":"NO",
                d.payable ? "ok":"bad"
            );

        document.getElementById("network").innerHTML =
            card("Block Height",num(d.height,0)) +
            card("Network Difficulty",num(d.difficulty,2),"small") +
            card("Block Value",num(d.blockValue,8)+" XBT","gold") +
            card("Network Hashrate",num(d.networkTh,2)+" TH/s","small");

        document.getElementById("window").innerHTML =
            card("Window Shares",num(d.windowShares,0)) +
            card("Total Window Work",d.windowWork) +
            card("Your Share",num(d.sharePercent,2)+"%","purple") +
            card(
                "Estimated Payout",
                num(d.estimatedPayoutXbt,8)+" XBT",
                "gold"
            ) +
            card("Blocks Found",num(d.blocks,0));

        document.getElementById("graphNow").textContent =
            num(d.hashrate,3)+" TH/s";

        drawGraph(d.hashHistory || []);

        const banner=document.getElementById("blockBanner");

        if(d.blocks>0){
            banner.style.display="block";
            banner.textContent =
                "🔥 BLOCKS FOUND: "+d.blocks+" — XBT POOL HAS HIT!";
        }else{
            banner.style.display="none";
        }

    }catch(e){
        document.getElementById("live").textContent="DATA ERROR";
        document.getElementById("live").className="live bad";
    }
}

refresh();
setInterval(refresh,5000);
</script>

</body>
</html>
"""

class Handler(BaseHTTPRequestHandler):

    def send_json(self,obj,status=200):
        body=json.dumps(obj).encode()

        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Cache-Control","no-store")
        self.end_headers()

        self.wfile.write(body)

    def do_GET(self):

        if self.path.startswith("/api/stats"):

            try:

                gateway=json.load(
                    urllib.request.urlopen(
                        GATEWAY,
                        timeout=3
                    )
                )

                prime=json.load(
                    urllib.request.urlopen(
                        PRIME,
                        timeout=3
                    )
                )

                s=gateway.get("stratum",{})
                accepted=gateway.get("shares_accepted",{})
                rejected=gateway.get("shares_rejected",{})
                job=gateway.get("job",{})

                window=prime.get("window",{})
                network=prime.get("network",{})
                blocks=prime.get("blocks",{})

                miners=window.get("miners",[])
                miner=miners[0] if miners else {}

                gateway_hash=float(
                    s.get("hashrate_ths",0) or 0
                )

                prime_hash_hs=float(
                    miner.get("hashrate_hs",0) or 0
                )

                prime_hash_th=prime_hash_hs/1_000_000_000_000

                # If Gateway's short-term estimate is currently zero,
                # fall back to Prime's ledger-based estimate.
                display_hash = (
                    gateway_hash
                    if gateway_hash > 0
                    else prime_hash_th
                )

                network_hashps=float(
                    s.get("network_hashps",0) or 0
                )

                history=[]

                for sample in gateway.get("hashrate",{}).get("history",[]):
                    try:
                        value=float(sample[1] or 0)
                        history.append(value)
                    except:
                        pass

                payout_sats=int(
                    miner.get("payout_sats",0) or 0
                )

                data={
                    "status":
                        gateway.get("status","Unknown"),

                    "uptime":
                        gateway.get("uptime","N/A"),

                    "connections":
                        s.get("connections",0),

                    "hashrate":
                        display_hash,

                    "primeHashrate":
                        prime_hash_th,

                    "hashHistory":
                        history,

                    "accepted":
                        accepted.get("count",0),

                    "rejected":
                        rejected.get("count",0),

                    "shareDifficulty":
                        accepted.get(
                            "diff",
                            prime.get("pool",{}).get(
                                "min_difficulty",0
                            )
                        ),

                    "height":
                        job.get(
                            "height",
                            network.get("tip_height",0)
                        ),

                    "difficulty":
                        job.get(
                            "difficulty",
                            network.get("difficulty",0)
                        ),

                    "blockValue":
                        job.get(
                            "value_btc",
                            (
                                network.get(
                                    "coinbase_value",0
                                ) or 0
                            )/100000000
                        ),

                    "networkTh":
                        network_hashps/1_000_000_000_000,

                    "windowShares":
                        window.get("shares",0),

                    "windowWork":
                        window.get("work","0"),

                    "identity":
                        miner.get("identity",""),

                    "minerWork":
                        miner.get("work","0"),

                    "sharePercent":
                        float(
                            miner.get(
                                "share_percent",0
                            ) or 0
                        ),

                    "estimatedPayoutXbt":
                        payout_sats/100000000,

                    "payable":
                        miner.get(
                            "payable",False
                        ),

                    "blocks":
                        blocks.get("found",0)
                }

                self.send_json(data)

            except Exception as e:
                self.send_json(
                    {"error":str(e)},
                    500
                )

        else:

            body=HTML.encode()

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/html"
            )
            self.send_header(
                "Cache-Control",
                "no-store"
            )
            self.end_headers()

            self.wfile.write(body)

HTTPServer(
    ("0.0.0.0",8080),
    Handler
).serve_forever()
