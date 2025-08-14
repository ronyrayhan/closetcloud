from flask import Flask, render_template_string, request, jsonify
import sqlite3

DB1_PATH = "old.db"
DB2_PATH = "new.db"

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Product Differences</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; }
        select { padding: 5px; font-size: 16px; margin-bottom: 15px; }
        table { border-collapse: collapse; width: 100%; margin-top: 10px; display: none; }
        th, td { border: 1px solid #ccc; padding: 8px; text-align: left; vertical-align: top; }
        th { background-color: #f2f2f2; cursor: pointer; }
        tr:nth-child(even) { background-color: #fafafa; }
        .price { background-color: #ffe4e4; }
        .title { background-color: #cce5ff; }
        .image { background-color: #fff3cd; }
        img { max-width: 80px; max-height: 80px; transition: transform 0.2s; cursor: pointer; }
        img:hover { transform: scale(2); }
        a.btn { display: inline-block; padding: 4px 8px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; font-size: 13px; }
        a.btn:hover { background: #0056b3; }
        button.sync { padding: 5px 10px; margin: 5px; cursor: pointer; }
        .hidden { display: none; }
        .pagination { margin-top: 10px; }
        .pagination button { margin: 2px; padding: 5px 10px; }
    </style>
</head>
<body>
    <h1>Product Differences</h1>

    <label for="diffType">Select Difference Type:</label>
    <select id="diffType" onchange="showTable()">
        <option value="price">Price Differences</option>
        <option value="title">Title Differences</option>
        <option value="image">Image Differences</option>
    </select>

    <div>
        <button class="sync" onclick="syncSelected('db1')">Sync Selected → DB1</button>
        <button class="sync" onclick="syncSelected('db2')">Sync Selected → DB2</button>
    </div>

    <!-- Price Table -->
    <table id="priceTable">
        <thead>
            <tr>
                <th><input type="checkbox" id="selectAllPrice" onclick="toggleAll('price')"></th>
                <th onclick="sortTable('price',1)">SKU</th>
                <th onclick="sortTable('price',2)">Title (OLD)</th>
                <th onclick="sortTable('price',3)">Price (OLD)</th>
                <th onclick="sortTable('price',4)">Title (NEW)</th>
                <th onclick="sortTable('price',5)">Price (NEW)</th>
                <th>Links</th>
            </tr>
        </thead>
        <tbody>
            {% for row in price_diff %}
            <tr>
                <td><input type="checkbox" class="rowCheckPrice" data-sku="{{ row['sku'] }}"></td>
                <td>{{ row['sku'] }}</td>
                <td>{{ row['title1'] }}</td>
                <td class="price">{{ row['price1'] }}</td>
                <td>{{ row['title2'] }}</td>
                <td class="price">{{ row['price2'] }}</td>
                <td>
                    <a class="btn" href="{{ row['url1'] }}" target="_blank">View DB1</a>
                    <a class="btn" href="{{ row['url2'] }}" target="_blank">View DB2</a>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <!-- Title Table -->
    <table id="titleTable">
        <thead>
            <tr>
                <th><input type="checkbox" id="selectAllTitle" onclick="toggleAll('title')"></th>
                <th onclick="sortTable('title',1)">SKU</th>
                <th onclick="sortTable('title',2)">Title (OLD )</th>
                <th onclick="sortTable('title',3)">Title (NEW)</th>
                <th>Links</th>
            </tr>
        </thead>
        <tbody>
            {% for row in title_diff %}
            <tr>
                <td><input type="checkbox" class="rowCheckTitle" data-sku="{{ row['sku'] }}"></td>
                <td>{{ row['sku'] }}</td>
                <td class="title">{{ row['title1'] }}</td>
                <td class="title">{{ row['title2'] }}</td>
                <td>
                    <a class="btn" href="{{ row['url1'] }}" target="_blank">View OLD</a>
                    <a class="btn" href="{{ row['url2'] }}" target="_blank">View NEW</a>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <!-- Image Table -->
    <table id="imageTable">
        <thead>
            <tr>
                <th><input type="checkbox" id="selectAllImage" onclick="toggleAll('image')"></th>
                <th onclick="sortTable('image',1)">SKU</th>
                <th>Image (DB1)</th>
                <th>Image (DB2)</th>
                <th>Links</th>
            </tr>
        </thead>
        <tbody>
            {% for row in image_diff %}
            <tr>
                <td><input type="checkbox" class="rowCheckImage" data-sku="{{ row['sku'] }}"></td>
                <td>{{ row['sku'] }}</td>
                <td class="image"><img src="{{ row['image1'] }}" alt="DB1 Image"></td>
                <td class="image"><img src="{{ row['image2'] }}" alt="DB2 Image"></td>
                <td>
                    <a class="btn" href="{{ row['url1'] }}" target="_blank">View DB1</a>
                    <a class="btn" href="{{ row['url2'] }}" target="_blank">View DB2</a>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <div class="pagination" id="pagination"></div>

<script>
function showTable(){
    var selected = document.getElementById("diffType").value;
    document.getElementById("priceTable").style.display = (selected=="price")?"table":"none";
    document.getElementById("titleTable").style.display = (selected=="title")?"table":"none";
    document.getElementById("imageTable").style.display = (selected=="image")?"table":"none";
    paginateTable(selected);
}

// Select all per table
function toggleAll(type){
    let checkboxes = document.querySelectorAll(".rowCheck"+capitalize(type));
    let selectAll = document.getElementById("selectAll"+capitalize(type));
    checkboxes.forEach(cb=>cb.checked=selectAll.checked);
}
function capitalize(s){return s.charAt(0).toUpperCase()+s.slice(1);}

// Sorting
function sortTable(tableType,n){
    var table = document.getElementById(tableType+"Table");
    var rows = Array.from(table.tBodies[0].rows);
    var dir = table.dataset.sortDir === "asc" ? "desc" : "asc";
    rows.sort((a,b)=>{
        let x=a.cells[n].innerText.toLowerCase();
        let y=b.cells[n].innerText.toLowerCase();
        if(x<y) return dir==="asc"? -1:1;
        if(x>y) return dir==="asc"? 1:-1;
        return 0;
    });
    rows.forEach(r=>table.tBodies[0].appendChild(r));
    table.dataset.sortDir=dir;
    paginateTable(tableType);
}

// Pagination
const rowsPerPage = 20;
let currentPage = 1;
function paginateTable(tableType){
    tableType = tableType || document.getElementById("diffType").value;
    let table = document.getElementById(tableType+"Table");
    let rows = Array.from(table.tBodies[0].rows);
    let totalPages = Math.ceil(rows.length/rowsPerPage);
    if(currentPage>totalPages) currentPage=1;
    rows.forEach((row,i)=>{
        row.style.display=(i>=(currentPage-1)*rowsPerPage && i<currentPage*rowsPerPage)?"":"none";
    });
    let pagination = document.getElementById("pagination");
    pagination.innerHTML="";
    for(let i=1;i<=totalPages;i++){
        let btn=document.createElement("button");
        btn.innerText=i;
        btn.onclick=function(){ currentPage=i; paginateTable(tableType); };
        if(i===currentPage) btn.style.fontWeight="bold";
        pagination.appendChild(btn);
    }
}
showTable();

// Sync selected rows
function syncSelected(targetDB){
    let type = document.getElementById("diffType").value;
    let selected=[];
    document.querySelectorAll(".rowCheck"+capitalize(type+":checked")).forEach(cb=>selected.push(cb.dataset.sku));
    if(selected.length==0){alert("Select at least one row"); return;}
    fetch("/sync",{
        method:"POST",
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({skus:selected,target:targetDB,type:type})
    }).then(resp=>resp.json()).then(data=>{alert(data.message); location.reload();});
}
</script>
</body>
</html>
"""

def fetch_diff(table):
    conn1 = sqlite3.connect(DB1_PATH)
    conn2 = sqlite3.connect(DB2_PATH)
    c1 = conn1.cursor()
    c2 = conn2.cursor()
    c1.execute("SELECT sku,title,price,image_url,url FROM products")
    data1 = c1.fetchall()
    c2.execute("SELECT sku,title,price,image_url,url FROM products")
    data2 = c2.fetchall()
    conn1.close()
    conn2.close()

    dict1 = {}
    for sku,title,price,img,url in data1:
        if sku not in dict1: dict1[sku]=[]
        dict1[sku].append({'title':title,'price':price,'image':img,'url':url})

    price_diff=[]
    title_diff=[]
    image_diff=[]
    for sku,title2,price2,img2,url2 in data2:
        if sku in dict1:
            for e in dict1[sku]:
                pdiff=e['price']!=price2
                tdiff=e['title']!=title2
                idiff=e['image']!=img2
                if pdiff:
                    price_diff.append({'sku':sku,'title1':e['title'],'price1':e['price'],
                        'title2':title2,'price2':price2,'url1':e['url'],'url2':url2})
                if tdiff:
                    title_diff.append({'sku':sku,'title1':e['title'],'title2':title2,'url1':e['url'],'url2':url2})
                if idiff:
                    image_diff.append({'sku':sku,'image1':e['image'],'image2':img2,'url1':e['url'],'url2':url2})
    return price_diff,title_diff,image_diff

@app.route("/")
def index():
    price_diff,title_diff,image_diff=fetch_diff("products")
    return render_template_string(HTML_TEMPLATE, price_diff=price_diff,title_diff=title_diff,image_diff=image_diff)

@app.route("/sync", methods=["POST"])
def sync():
    data = request.get_json()
    skus = data.get("skus", [])
    target = data.get("target")
    if target not in ["db1","db2"]:
        return jsonify({"message":"Invalid target"}),400
    source_db = DB2_PATH if target=="db1" else DB1_PATH
    target_db = DB1_PATH if target=="db1" else DB2_PATH
    src_conn = sqlite3.connect(source_db)
    tgt_conn = sqlite3.connect(target_db)
    src_cur = src_conn.cursor()
    tgt_cur = tgt_conn.cursor()
    for sku in skus:
        src_cur.execute("SELECT title,price,image_url,url FROM products WHERE sku=?",(sku,))
        src_entry=src_cur.fetchone()
        tgt_cur.execute("SELECT title,price,image_url,url FROM products WHERE sku=?",(sku,))
        tgt_entry=tgt_cur.fetchone()
        if src_entry and tgt_entry:
            updates=[]
            params=[]
            fields=["title","price","image_url","url"]
            for i,field in enumerate(fields):
                if src_entry[i]!=tgt_entry[i]:
                    updates.append(f"{field}=?")
                    params.append(src_entry[i])
            if updates:
                params.append(sku)
                tgt_cur.execute(f"UPDATE products SET {', '.join(updates)} WHERE sku=?",params)
    tgt_conn.commit()
    src_conn.close()
    tgt_conn.close()
    return jsonify({"message":f"Synced {len(skus)} SKU(s) to {target}"})

if __name__ == "__main__":
    app.run(debug=True)
