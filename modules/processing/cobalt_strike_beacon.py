"""
20JUN2018 - cs beacon config decoder
By Jason Reaves (@sysopfb) and Josh Platt
Free to use, attribute properly.
Will attempt to work on beacons from memory with already decoded configs as well
TODO
Add logic for other XOR keys
Transform parsing code needs work as well
"""
import glob
import sys
import re
import binascii
import struct
import json
import itertools

import os

from lib.cuckoo.common.abstracts import Processing

BeaconSettings = {1: "PROTOCOL", 2: "PORT", 3: "SLEEPTIME", 4: "MAXGET", 5: "JITTER", 6: "MAXDNS", 7: "PUBKEY",
                  8: "DOMAINS", 9: "USERAGENT", 10: "SUBMIT_URI", 11: "C2_RECOVER", 12: "C2_REQUEST", 13: "C2_POSTREQ",
                  14: "SPAWNTO", 15: "PIPENAME", 16: "KILLDATE_YEAR", 17: "KILLDATE_MONTH", 18: "KILLDATE_DAY",
                  19: "DNS_IDLE", 20: "DNS_SLEEP", 21: "SSH_HOST", 22: "SSH_PORT", 23: "SSH_USERNAME",
                  24: "SSH_PASSWORD", 25: "SSH_KEY", 26: "C2_VERB_GET", 27: "C2_VERB_POST", 28: "C2_CHUNK_POST",
                  29: "SPAWNTO_X86", 30: "SPAWNTO_X64", 31: "CRYPTO_SCHEME", 32: "PROXY_CONFIG", 33: "PROXY_USER",
                  34: "PROXY_PASSWORD", 35: "PROXY_BEHAVIOR", 36: "INJECT_OPTIONS", 37: "WATERMARK"}

SettingTypes = {0: "TYPE_NONE", 1: "TYPE_SHORT", 2: "TYPE_INT", 3: "TYPE_PTR"}
class cobalt_strike_beacon(Processing):

    key = "cobalt_strike"

    class conf_item:

        def __init__(self, beacon_index, setting_type, length, value):
            if beacon_index in BeaconSettings.keys():
                self.beaconSetting = BeaconSettings[beacon_index]
            else:
                self.beaconSetting = "UNKNOWN" + str(beacon_index)
            if setting_type in SettingTypes.keys():
                self.settingType = SettingTypes[setting_type]
            else:
                self.settingType = "UNKNOWN" + str(beacon_index)
            self.length = length
            if beacon_index == 7 or "UNKNOWN" in self.beaconSetting:
                if setting_type in [2, 3] and beacon_index != 7:
                    self.data = value
                else:
                    self.data = binascii.hexlify(str(value))
            elif beacon_index in [12, 13]:
                try:
                    self.data = self.parse_transformdata(value)
                except:
                    self.data = str(value)
            else:
                self.data = str(value)

        TransformStep = {1: "APPEND", 2: "PREPEND", 3: "BASE64", 4: "PRINT", 5: "PARAMETER", 6: "HEADER", 7: "BUILD",
                         8: "NETBIOS", 9: "_PARAMETER", 10: "_HEADER", 11: "NETBIOSU", 12: "URI_APPEND", 13: "BASE64_URL",
                         14: "STRREP", 15: "MASK"}

        # test_data = '\n\x00\x00\x00\x0bAccept: */*\x00\x00\x00\n\x00\x00\x00\x16Content-Type: text/xml\x00\x00\x00\n\x00\x00' \
        #            '\x00 X-Requested-With: XMLHttpRequest\x00\x00\x00\n\x00\x00\x00\x14Host: www.amazon.com\x00\x00\x00' \
        #            '\t\x00\x00\x00\nsz=160x600\x00\x00\x00\t\x00\x00\x00\x11oe=oe=ISO-8859-1;\x00\x00\x00\x07\x00\x00\x00\' \
        #            'x00\x00\x00\x00\x05\x00\x00\x00\x02sn\x00\x00\x00\t\x00\x00\x00\x06s=3717\x00\x00\x00\t\x00\x00' \
        #            '\x00"dc_ref=http%3A%2F%2Fwww.amazon.com\x00\x00\x00\x07\x00\x00\x00\x01\x00\x00\x00\x03\x00\x00\x00\x04'

        def parse_transformdata(self,data):
            config = []
            while len(data) > 5:
                (tstep, val, l,) = struct.unpack_from('>BHH', data)
                data = data[5:]
                if tstep in self.TransformStep.keys():
                    if tstep != 7:
                        temp = (self.TransformStep[tstep], val)
                        if l > 0:
                            s = str(data[:l])
                            temp += (s,)
                        data = data[l + 3:]
                    else:
                        (a, b,) = struct.unpack_from('>HH', data)
                        data = data[4:]
                        temp = ()
                        if val != 0:
                            temp += (self.TransformStep[val], l)
                        if a != 0:
                            temp += (self.TransformStep[a],)
                        if b != 0:
                            if b in [5, 6]:
                                (c, d) = struct.unpack_from('>HH', data)
                                data = data[4:]
                                temp += (self.TransformStep[b], str(data[:d]))
                                data = data[l + 3:]
                            elif b in [3]:
                                (c, d) = struct.unpack_from('>HH', data)
                                data = data[4:]
                                if d in [5, 6]:
                                    (e, f) = struct.unpack_from('>HH', data)
                                    data = data[4:]
                                    temp += ((self.TransformStep[b], self.TransformStep[d], str(data[:f])))
                                    data = data[f + 3:]

                            else:
                                temp += (self.TransformStep[b],)
                        temp = ('BUILD', temp)
                    config.append(temp)
            return config

        def get_jsonify(self):
            return {self.beaconSetting: str(self.data).decode("latin-1")}


    class beaconSettings:
        def __init__(self, blob):
            self.items = []
            (bsetting, stype, l,) = struct.unpack_from('>HHH', blob)
            while bsetting < 50 and stype < 10 and l < 1000 and len(blob) > 7:
                blob = blob[6:]
                data = blob[:l]
                blob = blob[l:]
                if stype == 3:
                    data = data.strip('\x00')
                elif stype == 2:
                    data = struct.unpack('>I', data)[0]
                elif stype == 1:
                    data = struct.unpack('>H', data)[0]
                self.items.append(cobalt_strike_beacon.conf_item(bsetting, stype, l, data))
                if len(blob) < 8:
                    break
                (bsetting, stype, l,) = struct.unpack_from('>HHH', blob)

        def get_jsonify(self):
            ret_val = {}
            for item in self.items:
                ret_val.update(item.get_jsonify())
            return ret_val

    def decoder(self,data):
        config = {}
        blob = bytearray(data)
        for i in range(len(blob)):
            blob[i] ^= 0x69
        start = re.findall('''\x00\x01\x00\x01\x00\x02\x00.\x00\x02\x00\x01''', blob)
        if len(start) > 0:
            start_offset = blob.find(start[0])
            bs = cobalt_strike_beacon.beaconSettings(blob[start_offset:])
            return bs.get_jsonify()
        pub_matches = re.findall('''\x30[\x00-\xff]{100,200}\x02\x03\x01\x00\x01\x00\x00''', blob)
        if pub_matches:
            config['PUBKEY'] = binascii.hexlify(pub_matches[0])

        pipe_matches = re.findall('''\\\\\\\\%s\\\\pipe\\\\[^\x00]+''', blob)
        if pipe_matches:
            config['PIPE'] = map(str, pipe_matches)

        ua_matches = re.findall('''Mozilla[^\x00]+''', blob)
        if ua_matches:
            config['UserAgents'] = map(str, ua_matches)

        ip_matches = re.findall('''\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}''', blob)
        if ip_matches:
            config['C2'] = map(str, ip_matches)
        uri_matches = re.findall('''\/[^\x2e\x00]+\.php''', blob)
        if uri_matches:
            config['URI'] = map(str, uri_matches)

        # Check if this is a mem dumped DLL with already decoded config
        if config == {}:
            start = re.findall('''\x00\x01\x00\x01\x00\x02\x00.\x00\x02\x00\x01''', data)
            if len(start) > 0:
                start_offset = data.find(start[0])
                bs = cobalt_strike_beacon.beaconSettings(data[start_offset:])
                return bs.get_jsonify()

        return config


    def config(self,data):

        return self.decoder(data)

    def run(self):
        files = map(lambda path: [os.path.abspath(os.path.join(path, p)) for p in os.listdir(path)], filter(lambda path: os.path.exists(path),[self.pmemory_path, self.dropped_path, self.buffer_path]))
        files.append([self.file_path])
        flat_files = list(itertools.chain.from_iterable(files))
        results = []
        for file in flat_files:
            data = open(file, 'rb').read()
            embedded_payload = re.search(r"[90]{6,}([a-f0-9]+)", data)
            decoded_payload = str(embedded_payload.group(1)).decode("hex")
            t = self.decoder(decoded_payload)
            results.append(t)
        return results
