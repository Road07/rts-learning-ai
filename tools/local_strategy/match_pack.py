"""Small standalone Godot-4 PCK reader/writer for private simulation packages."""
import hashlib
import struct

def unpack(data):
    if len(data)<104 or data[:4]!=b'GDPC':raise ValueError('Expected standalone Godot PCK')
    version,major,minor,patch,flags=struct.unpack_from('<5I',data,4)
    if version not in (3,4) or major!=4 or flags&~2:raise ValueError('Unsupported/encrypted PCK')
    base,directory=struct.unpack_from('<QQ',data,24);pos=directory
    count,=struct.unpack_from('<I',data,pos);pos+=4;result={}
    if count>100000:raise ValueError('PCK entry count too large')
    for _ in range(count):
        size,=struct.unpack_from('<I',data,pos);pos+=4
        if size>16384 or pos+size+36>len(data):raise ValueError('Invalid PCK directory')
        name=data[pos:pos+size].rstrip(b'\0').decode('utf-8');pos+=size
        offset,length=struct.unpack_from('<QQ',data,pos);digest=data[pos+16:pos+32];entry_flags,=struct.unpack_from('<I',data,pos+32);pos+=36
        start=base+offset;blob=data[start:start+length]
        if entry_flags or name in result or start<104 or start+length>directory or len(blob)!=length or hashlib.md5(blob).digest()!=digest:raise ValueError('Invalid PCK entry')
        result[name]=blob
    return result

def pack(entries):
    blobs=bytearray();directory=bytearray(struct.pack('<I',len(entries)))
    for name,content in sorted(entries.items()):
        path=name.encode()+b'\0';path+=b'\0'*(-len(path)%4)
        directory+=struct.pack('<I',len(path))+path+struct.pack('<QQ',len(blobs),len(content))+hashlib.md5(content).digest()+struct.pack('<I',0)
        blobs+=content
    return b'GDPC'+struct.pack('<5I',4,4,7,2,2)+struct.pack('<QQ',104,104+len(blobs))+b'\0'*64+blobs+directory
