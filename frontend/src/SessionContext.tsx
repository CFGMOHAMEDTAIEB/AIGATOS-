import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiGet, endpoints } from './api'
import type { OperationalContext } from './types'

type ContextValue = {
  contexts: OperationalContext[]
  active: OperationalContext | null
  activeSimulationId: string
  selectSimulation: (id:string)=>void
  loading: boolean
  error: Error | null
}

const OperationalSessionContext=createContext<ContextValue|null>(null)
const STORAGE_KEY='aigatos.activeSimulationId'

export function OperationalSessionProvider({children}:{children:ReactNode}){
  const query=useQuery({queryKey:['contexts','all'],queryFn:()=>apiGet<OperationalContext[]>(endpoints.contexts('all')),refetchInterval:15_000})
  const [activeSimulationId,setActiveSimulationId]=useState(()=>localStorage.getItem(STORAGE_KEY)??'')
  useEffect(()=>{
    if(!query.data?.length)return
    if(query.data.some(item=>item.simulation_id===activeSimulationId))return
    const preferred=query.data.find(item=>item.source==='LIVE_SIMULATION')??query.data[0]
    setActiveSimulationId(preferred.simulation_id)
  },[query.data,activeSimulationId])
  useEffect(()=>{if(activeSimulationId)localStorage.setItem(STORAGE_KEY,activeSimulationId)},[activeSimulationId])
  const value=useMemo<ContextValue>(()=>({
    contexts:query.data??[],
    active:query.data?.find(item=>item.simulation_id===activeSimulationId)??null,
    activeSimulationId,
    selectSimulation:setActiveSimulationId,
    loading:query.isLoading,
    error:query.error,
  }),[query.data,query.isLoading,query.error,activeSimulationId])
  return <OperationalSessionContext.Provider value={value}>{children}</OperationalSessionContext.Provider>
}

export function useOperationalSession(){
  const value=useContext(OperationalSessionContext)
  if(!value)throw new Error('OperationalSessionProvider is missing')
  return value
}
