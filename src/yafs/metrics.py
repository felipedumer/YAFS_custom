import csv

class Metrics:

    TIME_LATENCY = "time_latency"
    TIME_WAIT =  "time_wait"
    TIME_RESPONSE = "time_response"
    TIME_SERVICE = "time_service"
    TIME_TOTAL_RESPONSE = "time_total_response"

    WATT_SERVICE = "byService"
    WATT_UPTIME = "byUptime"


    def __init__(self, default_results_path=None):
        columns_event = ["id","type", "app", "module", "message","DES.src","DES.dst","TOPO.src","TOPO.dst","TOPO.srcLabel","TOPO.dstLabel","module.src","service", "time_in","time_out",
                         "time_emit","time_reception"]
        columns_link = ["id","type", "src", "dst", "srcLabel", "dstLabel", "app", "latency", "wait", "message", "ctime", "size","buffer"]
        columns_failure = [
            "id",
            "app",
            "message",
            "reason",
            "TOPO.src",
            "TOPO.dst",
            "TOPO.srcLabel",
            "TOPO.dstLabel",
            "ctime",
        ]

        path = "result"
        if  default_results_path is not None:
            path = default_results_path

        self.__filef = open("%s.csv" % path, "w")
        self.__filel = open("%s_link.csv"%path, "w")
        self.__filefail = open("%s_failure.csv"%path, "w")
        self.__ff = csv.writer(self.__filef)
        self.__ff_link = csv.writer(self.__filel)
        self.__ff_fail = csv.writer(self.__filefail)
        self.__ff.writerow(columns_event)
        self.__ff_link.writerow(columns_link)
        self.__ff_fail.writerow(columns_failure)

    def flush(self):
        self.__filef.flush()
        self.__filel.flush()

    def insert(self,value):

        self.__ff.writerow([value["id"],value["type"],
                    value["app"],
                    value["module"],
                    value["message"],
                    value["DES.src"],
                    value["DES.dst"],
                    value["TOPO.src"],
                    value["TOPO.dst"],
                    value.get("TOPO.srcLabel", ""),
                    value.get("TOPO.dstLabel", ""),
                    value["module.src"],
                    value["service"],
                    value["time_in"],
                    value["time_out"],
                    value["time_emit"],
                    value["time_reception"]
                            ])

    def insert_link(self, value):
        self.__ff_link.writerow([value["id"],value["type"],
                    value["src"],
                    value["dst"],
                    value.get("srcLabel", ""),
                    value.get("dstLabel", ""),
                    value["app"],
                    value["latency"],
                    value["wait"],
                    value["message"],
                    value["ctime"],
                    value["size"],
                    value["buffer"],

                            ])

    def close(self):
        self.__filef.close()
        self.__filel.close()
        self.__filefail.close()

    def insert_failure(self, value):
        self.__ff_fail.writerow([
            value.get("id", ""),
            value.get("app", ""),
            value.get("message", ""),
            value.get("reason", ""),
            value.get("TOPO.src", ""),
            value.get("TOPO.dst", ""),
            value.get("TOPO.srcLabel", ""),
            value.get("TOPO.dstLabel", ""),
            value.get("ctime", ""),
        ])
