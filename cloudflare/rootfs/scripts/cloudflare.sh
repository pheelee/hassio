#!/bin/sh

if [[ -z "$API_KEY" ]];then
  echo "Missing variable API_KEY"
  exit
fi

invoke_api() {
  METHOD=$1
  ENDPOINT=$2
  DATA=$@
  curl -s -X $METHOD "https://api.cloudflare.com/client/v4/$ENDPOINT" \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     $DATA
}

get_public_ip() {
  curl -sL ipinfo.io/ip
  #dig +short myip.opendns.com @resolver1.opendns.com
}

get_zoneId() {
	local ZONE=$1
	local CACHE=/tmp/$ZONE-id
	if [ ! -f $CACHE ]; then
		echo `invoke_api GET zones?name=$ZONE | jq -r ".result[0].id"` > $CACHE
	fi
	cat $CACHE	
}

get_recordId() {
	local ZONE_ID=$1
	local RECORD=$2
	local CACHE=/tmp/$RECORD-id
	if [ ! -f $CACHE ]; then
		echo `invoke_api GET zones/$ZONE_ID/dns_records?name=$RECORD | jq -r ".result[0].id"` > $CACHE
    fi
    cat $CACHE	
}

list_records() {
  invoke_api GET "zones/$ZONE_ID/dns_records"
}

update_record() {
  IP=$1
  ZONE_ID=$2
  RR_ID=$3
  RECORD=$4
  invoke_api PUT "zones/$ZONE_ID/dns_records/$RR_ID" --data '{"type":"A","name":"'$RECORD'","content":"'$IP'","ttl":1,"proxied":false}'

}

case $1 in 
  "update")
    ZONE=$2
    RECORD=$3
	ZONE_ID=`get_zoneId $ZONE`
	if [ $ZONE_ID = "null" ]; then
		echo "Zone not found"
		exit
	fi
	REC_ID=`get_recordId $ZONE_ID $RECORD`
	if [ $REC_ID = "null" ];then
		echo "Record not found"
		exit
	fi
    update_record `get_public_ip` $ZONE_ID $REC_ID $RECORD
    
esac

