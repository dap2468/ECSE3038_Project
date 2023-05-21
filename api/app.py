from fastapi import FastAPI,HTTPException,Request
from bson import ObjectId
import motor.motor_asyncio
from fastapi.middleware.cors import CORSMiddleware
import pydantic
import os
from dotenv import load_dotenv
from datetime import datetime,timedelta
import requests
import re


load_dotenv()
app= FastAPI()

origins=["https://simple-smart-hub-client.netlify.app"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client= motor.motor_asyncio.AsyncIOMotorClient(os.getenv('DOMAIN'))
db = client.status_database 

pydantic.json.ENCODERS_BY_TYPE[ObjectId]=str


###########################################################################################################################
#                                           FUNCTION
###########################################################################################################################
#SUNSET FUNCTION
def sunset():
    get_sunset=requests.get(f'https://api.sunrise-sunset.org/json?lat=18.1096&lng=-77.2975&date=today')
    s_json = get_sunset.json()
    time_date = s_json["results"]["sunset"] 
    time_date = datetime.strptime(time_date,'%I:%M:%S %p') + timedelta(hours=-5)
    time_date = datetime.strftime(time_date,'%H:%M:%S') 
    return time_date

#PARSE TIME FUNCTION
regex = re.compile(r'((?P<hours>\d+?)h)?((?P<minutes>\d+?)m)?((?P<seconds>\d+?)s)?')

def parse_time(time_str):
    parts = regex.match(time_str)
    if not parts:
        return
    parts = parts.groupdict()
    time_params = {}
    for name, param in parts.items():
        if param:
            time_params[name] = int(param)
    return timedelta(**time_params)



###########################################################################################################################
#                                           Webpage REQUESTS
###########################################################################################################################

#GET
@app.get("/graph", status_code=200)
async def graphpoints(request:Request,size: int):
    n = size
    list_of_status = await db["status"].find().sort("datetime",-1).to_list(n)
    list_of_status.reverse()
    return list_of_status

#PUT
@app.put("/settings",status_code=200)
async def setting(request:Request):
    
    setting = await request.json()
    variables = await db["settings"].find().to_list(1)
    modified = {}
    modified["user_temp"]=setting["user_temp"]
    if setting["user_light"]== "sunset":
        time=sunset()
    else:
        time = setting["user_light"]
    
    modified["user_light"]= (datetime.now().date()).strftime("%Y-%m-%dT")+time
    modified["light_time_off"]= ((datetime.strptime(modified["user_light"],'%Y-%m-%dT%H:%M:%S')+parse_time(setting["light_duration"])).strftime('%Y-%m-%dT%H:%M:%S'))

    if len(variables)==0:
         new_setting = await db["settings"].insert_one(modified)
         fixed = await db["settings"].find_one({"_id": new_setting.inserted_id })
         return fixed
    else:
        id=variables[0]["_id"]
        updated= await db["settings"].update_one({"_id":id},{"$set": modified})
        fixed = await db["settings"].find_one({"_id": id})
        if updated.modified_count>=1: 
            return fixed
    raise HTTPException(status_code=400,detail="Server cannot process the request due to something that is perceived to be a client error")



###########################################################################################################################
#                                           ESP REQUESTS
###########################################################################################################################

#POST  
@app.post("/api/status",status_code=201)
async def state_entry(request:Request):
    
    status = await request.json()
    status["date_time"]=(datetime.now()+timedelta(hours=-5)).strftime('%Y-%m-%dT%H:%M:%S')

    new = await db["status"].insert_one(status)
    update = await db["status"].find_one({"_id": new.inserted_id })
    if new.acknowledged == True:
        return update
    raise HTTPException(status_code=400,detail="Server cannot process the request due to something that is perceived to be a client error")


#GET
@app.get("/api/status")
async def getstate():
    status_now = await db["status"].find().sort("datetime",-1).to_list(1)
    settings_now = await db["settings"].find().to_list(1)

    dis_sensor = status_now[0]["presence"]
    time=datetime.strptime(datetime.strftime(datetime.now()+timedelta(hours=-5),'%H:%M:%S'),'%H:%M:%S')
    user_time=datetime.strptime(settings_now[0]["user_light"],'%H:%M:%S')
    off_time=datetime.strptime(settings_now[0]["light_time_off"],'%H:%M:%S')

    fan = ((float(status_now[0]["temperature"])>float(settings_now[0]["user_temp"])) and dis_sensor)
    light = (time>user_time) and (dis_sensor) and (time<off_time)
    
    states ={"fan":fan, "light":light}
    return states






















